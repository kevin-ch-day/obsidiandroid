"""Run manifest stage helpers.

This module isolates manifest assembly/writing so orchestration code can remain
focused on pipeline step ordering.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from config import app_config
from utils import artifacts
from utils import compliance
from utils import output_paths
from utils import run_manifest
from utils import display_utils as du
from utils.hash_utils import hash_payload
from analysis.pipeline.manifest.hashing import (
    canonical_csv_bytes,
    dataset_hash_from_sample_ids,
    sha256_hex,
)
from analysis.pipeline.manifest.runtime_support import (
    build_manifest_payload,
    build_registry_payload,
    resolve_run_root,
    runtime_diagnostics_dir as _manifest_runtime_diagnostics_dir,
    validate_run_scoped_artifact_paths as _manifest_validate_run_scoped_artifact_paths,
)
from analysis.pipeline.manifest.writer import write_manifest_atomic


def _runtime_diagnostics_dir() -> Path:
    """Resolve diagnostics output directory for current runtime mode."""
    return _manifest_runtime_diagnostics_dir()


def _validate_run_scoped_artifact_paths(
    *,
    artifact_list: list[str],
    run_root: Path,
    output_root: Path,
) -> None:
    """Enforce strict artifact path policy for run-scoped mode."""
    _manifest_validate_run_scoped_artifact_paths(
        artifact_list=artifact_list,
        run_root=run_root,
        output_root=output_root,
    )


def finalize_run_manifest_stage(
    manifest_context: dict,
    profile: dict,
    samples_df: pd.DataFrame | None,
    pipeline_results: dict | None,
    vendor_eval_df: pd.DataFrame | None,
    artifact_list: list[str],
) -> int:
    """Build and persist run manifest.

    Args:
        manifest_context: Run metadata including run ID and timestamp.
        profile: Active profile dictionary.
        samples_df: Prepared sample dataframe.
        pipeline_results: Runtime pipeline result dictionary.
        vendor_eval_df: Vendor evaluation dataframe.
        artifact_list: Runtime artifact path list.

    Returns:
        ``0`` when manifest is written successfully, otherwise ``1``.
    """
    try:
        run_id = str(manifest_context.get("run_id", "unknown"))
        paper_mode = bool(manifest_context.get("paper_mode", {}).get("resolved_value", False))
        evidence_mode = bool(profile.get("evidence_mode", False))
        output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
        diagnostics_dir = _runtime_diagnostics_dir()
        run_root = resolve_run_root(run_id=run_id, output_root=output_root)

        included_engines, excluded_engines, engine_names = _summarize_engine_lifecycle(
            pipeline_results
        )
        parser_list = _extract_parser_list(vendor_eval_df)
        dataset_hash = _compute_dataset_hash(samples_df=samples_df)
        registry_payload = build_registry_payload(
            manifest_context=manifest_context,
            samples_df=samples_df,
            run_id=run_id,
            paper_mode=paper_mode,
            evidence_mode=evidence_mode,
            dataset_hash=dataset_hash,
        )
        registry_path = diagnostics_dir / f"experiment_registry_{run_id}.json"
        registry_path.write_text(
            json.dumps(registry_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        manifest = build_manifest_payload(
            manifest_context=manifest_context,
            profile=profile,
            samples_df=samples_df,
            run_id=run_id,
            paper_mode=paper_mode,
            evidence_mode=evidence_mode,
            dataset_hash=dataset_hash,
            engine_names=engine_names,
            parser_list=parser_list,
            included_engines=included_engines,
            excluded_engines=excluded_engines,
        )
        split_meta = manifest.get("split", {}) if isinstance(manifest, dict) else {}
        duplicate_meta = manifest.get("duplicate_sha", {}) if isinstance(manifest, dict) else {}
        split_hash = str(split_meta.get("split_hash", ""))
        vendor_gate_debug_path = str(manifest.get("vendor_gate_debug_path", "") or "")
        model_config_snapshot_path = str(manifest.get("model_config_snapshot_path", "") or "")
        non_standard_features = bool(manifest.get("non_standard_features", False))
        ranking_path, ranking_hash = _export_engine_ranking_tiers(
            run_root=run_root,
            run_id=run_id,
            evidence_mode=evidence_mode,
            weights_df=pipeline_results.get("weights_df") if isinstance(pipeline_results, dict) else None,
        )
        if ranking_path:
            artifact_list.append(str(ranking_path))
        parser_final_path = _export_parser_quality_final(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            weights_df=pipeline_results.get("weights_df") if isinstance(pipeline_results, dict) else None,
        )
        if parser_final_path:
            artifact_list.append(str(parser_final_path))
        manifest["engine_ranking_hash"] = ranking_hash
        manifest["engine_list_hash"] = hash_payload(engine_names)
        _write_manifest_with_pointer(
            manifest=manifest,
            run_id=run_id,
            paper_mode=paper_mode,
            run_root=Path(str(getattr(app_config, "RUNTIME_RUN_ROOT", output_root))),
        )
        onepager_path = _write_run_summary_onepager(
            run_id=run_id,
            diagnostics_dir=diagnostics_dir,
            profile=profile,
            manifest_context=manifest_context,
            manifest=manifest,
            compliance_path=diagnostics_dir / f"paper_mode_compliance_report_{run_id}.json",
        )
        if onepager_path is not None:
            if str(onepager_path) not in artifact_list:
                artifact_list.append(str(onepager_path))
        contract_snapshot_path = _write_experiment_contract_snapshot(
            run_id=run_id,
            diagnostics_dir=diagnostics_dir,
            profile=profile,
            manifest_context=manifest_context,
            manifest=manifest,
        )
        if contract_snapshot_path is not None and str(contract_snapshot_path) not in artifact_list:
            artifact_list.append(str(contract_snapshot_path))
        artifact_index_path = _write_run_artifact_index(
            run_id=run_id,
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
        )
        if artifact_index_path is not None and str(artifact_index_path) not in artifact_list:
            artifact_list.append(str(artifact_index_path))
        trained_registry_path, trained_family_count = _export_trained_family_registry(
            samples_df=samples_df,
            run_id=run_id,
            diagnostics_dir=diagnostics_dir,
        )
        if trained_registry_path and str(trained_registry_path) not in artifact_list:
            artifact_list.append(str(trained_registry_path))
        confusion_provenance_path = _export_confusion_matrix_provenance(
            run_root=run_root,
            run_id=run_id,
            diagnostics_dir=diagnostics_dir,
            manifest_context=manifest_context,
            trained_family_count=trained_family_count,
            evidence_mode=evidence_mode,
        )
        if confusion_provenance_path and str(confusion_provenance_path) not in artifact_list:
            artifact_list.append(str(confusion_provenance_path))
        manifest["cohort_limitation_summary"] = _build_cohort_limitation_summary(samples_df=samples_df)
        paper_exports = _build_strict_paper2_exports(
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            samples_df=samples_df,
            manifest_context=manifest_context,
            evidence_mode=evidence_mode,
            paper_mode=paper_mode,
        )
        if isinstance(paper_exports, dict):
            manifest["paper2_export_profile"] = paper_exports.get("profile", {})
            paper_profile = paper_exports.get("profile", {}) if isinstance(paper_exports.get("profile", {}), dict) else {}
            manifest["paper_export_status"] = {
                "enabled": bool(paper_profile.get("strict_profile_enabled", False)),
                "reason": str(paper_profile.get("reason", "produced" if bool(paper_mode) else "paper_mode_disabled")),
            }
            for path in paper_exports.get("artifact_paths", []):
                if path not in artifact_list:
                    artifact_list.append(path)
        else:
            manifest["paper_export_status"] = {
                "enabled": False,
                "reason": "not_requested",
            }

        if isinstance(pipeline_results, dict):
            known_model_keys = {
                "random_forest",
                "balanced_random_forest",
                "xgboost",
                "logistic_regression",
            }
            trained_models = sorted([k for k in pipeline_results.keys() if k in known_model_keys])
            manifest["trained_models"] = trained_models

        manifest_writer = artifacts.ManifestWriter(run_root=run_root, paper_mode=paper_mode)
        if split_meta.get("split_audit_path"):
            _try_add_artifact(
                writer=manifest_writer,
                key=artifacts.ArtifactKey.SPLIT_AUDIT_CSV,
                file_path=Path(str(split_meta.get("split_audit_path"))),
                content_type="text/csv",
                description="Split freeze audit",
            )
        if duplicate_meta.get("report_path"):
            _try_add_artifact(
                writer=manifest_writer,
                key=artifacts.ArtifactKey.DUPLICATE_SHA_REPORT_CSV,
                file_path=Path(str(duplicate_meta.get("report_path"))),
                content_type="text/csv",
                description="Duplicate sha256 report",
            )
        if vendor_gate_debug_path:
            _try_add_artifact(
                writer=manifest_writer,
                key=artifacts.ArtifactKey.VENDOR_GATE_DEBUG_CSV,
                file_path=Path(vendor_gate_debug_path),
                content_type="text/csv",
                description="Vendor gate debug table",
            )
        if model_config_snapshot_path:
            _try_add_artifact(
                writer=manifest_writer,
                key=artifacts.ArtifactKey.MODEL_CONFIG_SNAPSHOT_JSON,
                file_path=Path(model_config_snapshot_path),
                content_type="application/json",
                description="Model configuration snapshot",
            )
        cohort_contract_path = diagnostics_dir / f"cohort_filter_contract_{run_id}.json"
        if cohort_contract_path.exists():
            _try_add_artifact(
                writer=manifest_writer,
                key=artifacts.ArtifactKey.COHORT_FILTER_CONTRACT_JSON,
                file_path=cohort_contract_path,
                content_type="application/json",
                description="Cohort filter contract",
            )
        _try_add_artifact(
            writer=manifest_writer,
            key=artifacts.ArtifactKey.EXPERIMENT_REGISTRY_JSON,
            file_path=registry_path,
            content_type="application/json",
            description="Experiment registry",
        )
        if onepager_path is not None:
            _try_add_artifact(
                writer=manifest_writer,
                key=artifacts.ArtifactKey.RUN_SUMMARY_ONEPAGER_MD,
                file_path=onepager_path,
                content_type="text/markdown",
                description="Run summary one-pager",
            )
        if contract_snapshot_path is not None:
            _try_add_artifact(
                writer=manifest_writer,
                key=artifacts.ArtifactKey.EXPERIMENT_CONTRACT_SNAPSHOT_JSON,
                file_path=contract_snapshot_path,
                content_type="application/json",
                description="Experiment contract snapshot",
            )
        run_paths_manifest_path = diagnostics_dir / f"run_paths_manifest_{run_id}.json"
        manifest_writer.write_json(
            output_path=run_paths_manifest_path,
            run_id=run_id,
            profile_name=str(profile.get("profile_id", "unknown")),
        )
        manifest["excluded_non_run_scoped_count"] = int(
            getattr(manifest_writer, "excluded_non_run_scoped_count", 0)
        )
        taxonomy_summary_path = diagnostics_dir / f"taxonomy_consistency_summary_{run_id}.json"
        taxonomy_type_rows_evaluated = 0
        if taxonomy_summary_path.exists():
            try:
                taxonomy_payload = json.loads(taxonomy_summary_path.read_text(encoding="utf-8"))
                taxonomy_type_rows_evaluated = int(taxonomy_payload.get("type_rows_evaluated", 0) or 0)
            except Exception:
                taxonomy_type_rows_evaluated = 0

        compliance_checks = _build_paper_compliance_checks(
            paper_mode=paper_mode,
            split_hash=split_hash,
            split_audit_path=str(split_meta.get("split_audit_path", "")),
            duplicate_report_path=str(duplicate_meta.get("report_path", "")),
            duplicate_count=int(duplicate_meta.get("duplicate_sha_groups", 0) or 0),
            invalid_sha_count=int(duplicate_meta.get("invalid_sha_count", 0) or 0),
            vendor_gate_debug_path=vendor_gate_debug_path,
            run_paths_manifest_path=str(run_paths_manifest_path),
            experiment_registry_path=str(registry_path),
            taxonomy_summary_path=str(taxonomy_summary_path),
            taxonomy_type_rows_evaluated=taxonomy_type_rows_evaluated,
        )
        compliance_report = compliance.build_compliance_report(run_id=run_id, checks=compliance_checks)
        compliance_path = diagnostics_dir / f"paper_mode_compliance_report_{run_id}.json"
        compliance.write_compliance_report(compliance_path, compliance_report)
        manifest["paper_mode_compliance_report"] = str(compliance_path)
        _validate_run_scoped_artifact_paths(
            artifact_list=artifact_list,
            run_root=run_root,
            output_root=output_root,
        )
        manifest["artifact_list"] = sorted(set(artifact_list))
        _write_manifest_with_pointer(
            manifest=manifest,
            run_id=run_id,
            paper_mode=paper_mode,
            run_root=run_root,
        )
        readiness_status = "ready"
        failed_checks: list[str] = []
        evidence_artifacts: dict[str, str] = {}
        if evidence_mode:
            evidence_artifacts = _build_paper2_pack(
                run_root=run_root,
                run_id=run_id,
                samples_df=samples_df,
                manifest=manifest,
                manifest_context=manifest_context,
                ranking_path=ranking_path,
            )
            mandatory = [
                "dataset_characterization.json",
                "engine_ranking_tiers.csv",
                "consensus_distribution.csv",
                "consensus_distribution.png",
                "model_metrics.json",
                "confusion_matrix_primary.png",
                "manifest.json",
                "evidence_compliance_summary.json",
            ]
            pack_dir = run_root / "paper2_pack"
            missing = [name for name in mandatory if not (pack_dir / name).exists()]
            if missing:
                failed_checks.append("mandatory_artifacts_present")
            if str(manifest_context.get("integrity_error", "")).strip():
                failed_checks.append("integrity_pass")
            if manifest.get("vendor_fallback_used", False):
                failed_checks.append("fallback_used")
            if non_standard_features:
                failed_checks.append("non_standard_features")
            if not manifest.get("dataset_hash"):
                failed_checks.append("dataset_hash_present")
            if not manifest.get("engine_list_hash"):
                failed_checks.append("engine_list_hash_present")
            if not manifest.get("engine_ranking_hash"):
                failed_checks.append("engine_ranking_hash_present")
            if not manifest.get("split", {}).get("split_hash"):
                failed_checks.append("deterministic_split_hash_present")
            if failed_checks:
                readiness_status = "not_ready"
            readiness_path = _write_evidence_readiness(
                run_root=run_root,
                status=readiness_status,
                failed_checks=failed_checks,
                manifest=manifest,
                integrity_reason=str(manifest_context.get("integrity_error", "")),
            )
            artifact_list.append(str(readiness_path))
            if readiness_status != "ready":
                du.print_warning(
                    "[EVIDENCE] Run marked not_ready. "
                    f"Failed checks: {', '.join(sorted(set(failed_checks)))}"
                )
                _write_run_summary_json(
                    run_root=run_root,
                    diagnostics_dir=diagnostics_dir,
                    manifest_context=manifest_context,
                    manifest=manifest,
                    result_code=1,
                )
                return 1
        if paper_mode and str(compliance_report.get("overall_status")) != "pass":
            du.print_error(f"[PAPER] Compliance failed. Report: {compliance_path}")
            _write_run_summary_json(
                run_root=run_root,
                diagnostics_dir=diagnostics_dir,
                manifest_context=manifest_context,
                manifest=manifest,
                result_code=1,
            )
            return 1
        _write_run_summary_json(
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            manifest_context=manifest_context,
            manifest=manifest,
            result_code=0,
        )
        return 0
    except Exception as exc:
        try:
            run_id = str(manifest_context.get("run_id", "unknown"))
            output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
            runtime_root_raw = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
            run_root = Path(runtime_root_raw) if runtime_root_raw else (output_root / "runs" / run_id)
            evidence_mode = bool(profile.get("evidence_mode", False))
            diagnostics_dir = _runtime_diagnostics_dir()
            _write_evidence_readiness(
                run_root=run_root,
                status="not_ready",
                failed_checks=["manifest_complete"],
                manifest={"run_id": run_id, "evidence_mode": evidence_mode},
                integrity_reason=str(exc),
            )
            _write_evidence_compliance_stub(
                run_root=run_root,
                run_id=run_id,
                evidence_mode=evidence_mode,
                reason=str(exc),
            )
            _write_run_summary_json(
                run_root=run_root,
                diagnostics_dir=diagnostics_dir,
                manifest_context=manifest_context,
                manifest={
                    "run_id": run_id,
                    "profile_params": profile,
                    "timestamp_utc": manifest_context.get("timestamp_utc"),
                    "evidence_mode": evidence_mode,
                },
                result_code=1,
            )
        except Exception:
            pass
        du.print_error(f"[INTEGRITY] Run manifest finalization failed: {exc}")
        return 1


def _write_run_summary_json(
    *,
    run_root: Path,
    diagnostics_dir: Path,
    manifest_context: dict[str, Any],
    manifest: dict[str, Any],
    result_code: int,
) -> Path | None:
    """Write canonical run-summary JSON for operator history and health views."""
    try:
        run_id = str(manifest.get("run_id", manifest_context.get("run_id", "unknown")))
        profile = manifest.get("profile_params", {}) if isinstance(manifest.get("profile_params"), dict) else {}
        model_summary = manifest.get("model_summary", {}) if isinstance(manifest.get("model_summary"), dict) else {}
        configured_status = str(manifest_context.get("run_status", "") or "").strip().lower()
        failure_reason = str(
            manifest_context.get("failure_reason", "") or manifest_context.get("integrity_error", "")
        ).strip()
        if configured_status in {"complete", "partial", "failed"}:
            run_status = configured_status
        elif failure_reason or int(result_code) != 0:
            run_status = "failed"
        elif str(manifest_context.get("completed_stage", "") or "").strip().lower() not in {"", "manifest"}:
            run_status = "partial"
        else:
            run_status = "complete"

        completed_stage = str(manifest_context.get("completed_stage", "") or "").strip()
        if not completed_stage:
            completed_stage = "manifest" if run_status == "complete" else str(
                manifest_context.get("current_stage", "") or "unknown"
            ).strip()

        payload = {
            "schema_version": "1.0",
            "run_id": run_id,
            "profile_id": str(profile.get("profile_id", "unknown")),
            "timestamp_utc": str(manifest.get("timestamp_utc", "") or manifest_context.get("timestamp_utc", "")),
            "run_status": run_status,
            "completed_stage": completed_stage,
            "failed_stage": str(manifest_context.get("failed_stage", "") or "").strip() or None,
            "failure_reason": failure_reason or None,
            "cohort_size": int(manifest.get("cohort_size", 0) or 0),
            "selected_vendor_count": manifest.get("selected_vendor_count"),
            "vendor_constrained_run_flag": bool(manifest.get("vendor_constrained_run_flag", False)),
            "pipeline_runtime_sec": manifest_context.get("pipeline_runtime_sec"),
            "top_model": str(model_summary.get("top_model", "") or "").strip() or None,
            "top_macro_f1": model_summary.get("top_macro_f1"),
            "model_summary": model_summary,
            "manifest_path": str(run_root / "run_manifest.json"),
            "run_root": str(run_root),
            "paper_mode": bool((manifest.get("paper_mode") or {}).get("resolved_value", False)),
            "evidence_mode": bool(manifest.get("evidence_mode", False)),
            "result_code": int(result_code),
        }

        run_summary_path = run_root / "run_summary.json"
        run_summary_run_path = diagnostics_dir / f"run_summary_{run_id}.json"
        run_summary_latest_path = diagnostics_dir / "run_summary.latest.json"
        encoded = json.dumps(payload, indent=2, sort_keys=True)
        run_summary_path.write_text(encoded, encoding="utf-8")
        run_summary_run_path.write_text(encoded, encoding="utf-8")
        run_summary_latest_path.write_text(encoded, encoding="utf-8")
        return run_summary_path
    except Exception as exc:
        du.print_warning(f"[SUMMARY] Failed to write canonical run summary: {exc}")
        return None


def _write_run_summary_onepager(
    *,
    run_id: str,
    diagnostics_dir: Path,
    profile: dict[str, Any],
    manifest_context: dict[str, Any],
    manifest: dict[str, Any],
    compliance_path: Path,
) -> Path | None:
    """Write a concise run-summary markdown artifact for quick reviewer/operator use."""
    try:
        paper_mode_data = manifest_context.get("paper_mode", {})
        model_summary = manifest_context.get("model_summary", {})
        stage_timings = manifest_context.get("stage_timings_sec", {})
        split_meta = manifest.get("split", {}) if isinstance(manifest, dict) else {}
        duplicate_meta = manifest.get("duplicate_sha", {}) if isinstance(manifest, dict) else {}

        lines = [
            f"# Run Summary One-Pager ({run_id})",
            "",
            "## Context",
            f"- run_id: `{run_id}`",
            f"- profile_id: `{profile.get('profile_id', 'unknown')}`",
            f"- paper_mode: `{bool(paper_mode_data.get('resolved_value', False))}` (source=`{paper_mode_data.get('source', 'unknown')}`)",
            f"- cohort_size: `{manifest.get('cohort_size', 0)}`",
            f"- selected_vendor_count: `{manifest.get('selected_vendor_count', 0)}`",
            "",
            "## Governance",
            f"- split_hash: `{split_meta.get('split_hash', '')}`",
            f"- split_audit: `{split_meta.get('split_audit_path', '')}`",
            f"- duplicate_sha_groups: `{duplicate_meta.get('duplicate_sha_groups', 0)}`",
            f"- invalid_sha_count: `{duplicate_meta.get('invalid_sha_count', 0)}`",
            f"- vendor_set_hash: `{manifest.get('vendor_set_hash', '')}`",
            f"- compliance_report: `{compliance_path}`",
            "",
            "## Model Snapshot",
        ]
        if isinstance(model_summary, dict) and model_summary:
            lines.extend(
                [
                    f"- top_model: `{model_summary.get('top_model', '')}`",
                    f"- top_macro_f1: `{model_summary.get('top_macro_f1', '')}`",
                ]
            )
            model_rows = model_summary.get("model_rows", [])
            if isinstance(model_rows, list) and model_rows:
                lines.append("")
                lines.append("| model | macro_f1 | weighted_f1 | accuracy |")
                lines.append("|---|---:|---:|---:|")
                for row in model_rows:
                    lines.append(
                        f"| {row.get('model', '')} | {row.get('macro_f1', '')} | "
                        f"{row.get('weighted_f1', '')} | {row.get('accuracy', '')} |"
                    )
        else:
            lines.append("- model summary not available (run stopped before training).")

        if isinstance(stage_timings, dict) and stage_timings:
            lines.extend(["", "## Stage Timings (sec)"])
            for stage_name, sec in stage_timings.items():
                lines.append(f"- {stage_name}: `{sec}`")

        onepager_path = diagnostics_dir / f"run_summary_onepager_{run_id}.md"
        latest_path = diagnostics_dir / "run_summary_onepager.latest.md"
        payload = "\n".join(lines).strip() + "\n"
        onepager_path.write_text(payload, encoding="utf-8")
        latest_path.write_text(payload, encoding="utf-8")
        return onepager_path
    except Exception as exc:
        du.print_warning(f"[SUMMARY] Failed to write run one-pager: {exc}")
        return None


def _write_experiment_contract_snapshot(
    *,
    run_id: str,
    diagnostics_dir: Path,
    profile: dict[str, Any],
    manifest_context: dict[str, Any],
    manifest: dict[str, Any],
) -> Path | None:
    """Write one-file snapshot of experiment contract decisions for reproducibility."""
    try:
        split_meta = manifest.get("split", {}) if isinstance(manifest, dict) else {}
        paper_mode_data = manifest_context.get("paper_mode", {})
        profile_gates = profile.get("cohort_gates", {}) if isinstance(profile, dict) else {}
        profile_id = str(profile.get("profile_id", "unknown"))
        split_hash = str(split_meta.get("split_hash", ""))
        model_config_hash = str(manifest_context.get("model_config_hash", ""))
        series_id = _compute_experiment_series_id(profile_id=profile_id, split_hash=split_hash)
        previous_series_contract = _load_previous_series_contract(
            diagnostics_dir=diagnostics_dir,
            series_id=series_id,
            current_run_id=run_id,
        )
        previous_run_id = str(previous_series_contract.get("run_id", "")) if previous_series_contract else ""
        previous_model_config_hash = (
            str((previous_series_contract.get("model_contract") or {}).get("model_config_hash", ""))
            if previous_series_contract
            else ""
        )
        no_retuning_consistent = bool(
            not previous_model_config_hash
            or not model_config_hash
            or previous_model_config_hash == model_config_hash
        )

        contract = {
            "schema_version": "1.0",
            "run_id": run_id,
            "profile_id": profile_id,
            "experiment_series": {
                "series_id": series_id,
                "series_key": {
                    "profile_id": profile_id,
                    "split_hash": split_hash,
                },
                "previous_run_id_in_series": previous_run_id or None,
                "previous_model_config_hash_in_series": previous_model_config_hash or None,
                "model_config_hash_stable_with_series": bool(no_retuning_consistent),
            },
            "paper_mode": {
                "enabled": bool(paper_mode_data.get("resolved_value", False)),
                "source": str(paper_mode_data.get("source", "unknown")),
            },
            "target_task": {
                "label_field": "family_canonical",
                "task_type": "multiclass_classification",
                "primary_metric": "macro_f1_mean_cv5",
            },
            "split_contract": {
                "split_hash": split_hash,
                "split_seed": split_meta.get("split_seed"),
                "split_algorithm": split_meta.get("split_algorithm"),
                "split_algorithm_version": split_meta.get("split_algorithm_version"),
                "cv_protocol": {
                    "stratified_kfold_splits": int(getattr(app_config, "CV_FOLDS", 5)),
                    "repeats": int(getattr(app_config, "CV_REPEATS", 1)),
                    "fixed_seed": int(getattr(app_config, "RANDOM_STATE", 42)),
                },
            },
            "perturbation_contract": {
                "consensus_min_malicious_detections": profile_gates.get("min_malicious_detections"),
                "family_cap": profile_gates.get("family_cap"),
                "family_cap_seed": profile_gates.get("family_cap_seed"),
                "unknown_type_excluded": bool(
                    profile_gates.get(
                        "exclude_unknown_type_slug",
                        bool(getattr(app_config, "PAPER_MODE_ENABLED", False)),
                    )
                ),
            },
            "feature_contract": {
                "sample_level_only": True,
                "label_derived_features_forbidden": True,
                "family_aggregate_features_forbidden": True,
                "post_split_stats_forbidden": True,
                "temporal_features_forbidden": True,
            },
            "model_contract": {
                "no_model_retuning_across_perturbations": bool(no_retuning_consistent),
                "model_config_hash": model_config_hash,
            },
            "material_change_rule": {
                "primary_abs_delta_macro_f1_gt": float(
                    getattr(app_config, "PAPER_MATERIAL_CHANGE_ABS_DELTA_MACRO_F1", 0.02)
                ),
                "secondary_relative_drop_pct_gt": float(
                    getattr(app_config, "PAPER_MATERIAL_CHANGE_REL_DROP_PCT", 5.0)
                ),
                "ci_overrides_threshold": False,
            },
        }
        out_path = diagnostics_dir / f"experiment_contract_snapshot_{run_id}.json"
        latest_path = diagnostics_dir / "experiment_contract_snapshot.latest.json"
        payload = json.dumps(contract, indent=2, sort_keys=True)
        out_path.write_text(payload, encoding="utf-8")
        latest_path.write_text(payload, encoding="utf-8")
        return out_path
    except Exception as exc:
        du.print_warning(f"[SUMMARY] Failed to write experiment contract snapshot: {exc}")
        return None


def _compute_experiment_series_id(*, profile_id: str, split_hash: str) -> str:
    """Build a stable series identifier for cross-run comparability checks."""
    payload = {"profile_id": str(profile_id), "split_hash": str(split_hash)}
    return hash_payload(payload)[:12]


def _load_previous_series_contract(
    *,
    diagnostics_dir: Path,
    series_id: str,
    current_run_id: str,
) -> dict[str, Any]:
    """Load latest contract snapshot when it belongs to the same series."""
    latest_path = diagnostics_dir / "experiment_contract_snapshot.latest.json"
    if not latest_path.exists():
        return {}
    try:
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    latest_run_id = str(payload.get("run_id", ""))
    if latest_run_id == current_run_id:
        return {}
    payload_series = str((payload.get("experiment_series") or {}).get("series_id", ""))
    if payload_series != series_id:
        return {}
    return payload


def _try_add_artifact(
    writer: artifacts.ManifestWriter,
    key: str,
    file_path: Path,
    content_type: str,
    description: str,
) -> None:
    """Add artifact to manifest writer if file exists."""
    if not file_path.exists():
        return
    writer.add_file(
        artifact_key=key,
        path=file_path.resolve(),
        content_type=content_type,
        description=description,
    )


def _write_manifest_with_pointer(
    *,
    manifest: dict[str, Any],
    run_id: str,
    paper_mode: bool,
    run_root: Path,
) -> None:
    """Write canonical manifest and update pointer file for latest run."""
    manifest_payload = dict(manifest)
    manifest_payload["manifest_schema_version"] = run_manifest.MANIFEST_SCHEMA_VERSION
    pointer_payload = {
        "run_id": run_id,
        "created_at_utc": manifest.get("timestamp_utc", ""),
        "run_root": str(run_root).replace("\\", "/"),
    }
    canonical_path = run_root / "run_manifest.json"
    write_manifest_atomic(
        target_path=canonical_path,
        payload=manifest_payload,
    )
    # `run_manifest.latest.json` is always the full manifest schema.
    run_manifest.write_run_manifest(manifest_payload)
    pointer_path = Path(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")) / "diagnostics" / "latest_run_pointer.json"
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_text(
        json.dumps(pointer_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_promoted_latest_run_pointer(pointer_payload=pointer_payload)


def _write_promoted_latest_run_pointer(*, pointer_payload: dict[str, Any]) -> None:
    """Write stable promoted pointers for human/tester run discovery."""
    run_id = str(pointer_payload.get("run_id", "")).strip()
    if not run_id:
        return
    promoted_root = output_paths.promoted_root()
    promoted_root.mkdir(parents=True, exist_ok=True)
    (promoted_root / "latest_run.txt").write_text(f"{run_id}\n", encoding="utf-8")
    (promoted_root / "latest_run_manifest.json").write_text(
        json.dumps(pointer_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_run_artifact_index(
    *,
    run_id: str,
    run_root: Path,
    diagnostics_dir: Path,
) -> Path | None:
    """Write a concise run-scoped index for tester/QA artifact discovery."""
    try:
        lines = [
            f"# Run Artifact Index ({run_id})",
            "",
            "Authoritative source: all artifacts under this run root.",
            "",
            f"- run_root: `{run_root}`",
            f"- paper_exports: `{run_root / 'paper_exports'}`",
            f"- bundles/permission_trends: `{run_root / 'bundles' / 'permission_trends'}`",
            f"- diagnostics: `{diagnostics_dir}`",
            f"- models: `{run_root / 'models'}`",
            f"- conf_matrices: `{run_root / 'conf_matrices'}`",
            "",
            "Notes:",
            "- Root-level latest/promoted paths are convenience mirrors only.",
            "- Use run-scoped artifacts for paper evidence and QA checks.",
        ]
        out_path = diagnostics_dir / "run_artifact_index.md"
        out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return out_path
    except Exception as exc:
        du.print_warning(f"[SUMMARY] Failed to write run artifact index: {exc}")
        return None


def _build_paper_compliance_checks(
    *,
    paper_mode: bool,
    split_hash: str,
    split_audit_path: str,
    duplicate_report_path: str,
    duplicate_count: int,
    invalid_sha_count: int,
    vendor_gate_debug_path: str,
    run_paths_manifest_path: str,
    experiment_registry_path: str,
    taxonomy_summary_path: str,
    taxonomy_type_rows_evaluated: int,
) -> list[dict[str, Any]]:
    """Build compliance check payload rows."""
    checks: list[dict[str, Any]] = []
    checks.append(
        _check(
            "split_hash_present",
            bool(split_hash),
            "fatal",
            "split_hash missing",
            artifacts.ArtifactKey.SPLIT_AUDIT_CSV,
            "Ensure split audit exports before training.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _check(
            "split_audit_exists",
            bool(split_audit_path) and Path(split_audit_path).exists(),
            "fatal",
            "split audit artifact missing",
            artifacts.ArtifactKey.SPLIT_AUDIT_CSV,
            "Export split_freeze_audit_<run_id>.csv prior to training.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _check(
            "duplicate_report_exists",
            bool(duplicate_report_path) and Path(duplicate_report_path).exists(),
            "fatal",
            "duplicate sha report missing",
            artifacts.ArtifactKey.DUPLICATE_SHA_REPORT_CSV,
            "Run duplicate SHA audit after alignment.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _check(
            "duplicate_sha_clean",
            duplicate_count == 0 and invalid_sha_count == 0,
            "fatal",
            f"duplicate/invalid sha detected (dup={duplicate_count}, invalid={invalid_sha_count})",
            artifacts.ArtifactKey.DUPLICATE_SHA_REPORT_CSV,
            "Fix sample universe and rerun paper mode.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _check(
            "vendor_gate_debug_exists",
            bool(vendor_gate_debug_path) and Path(vendor_gate_debug_path).exists(),
            "fatal",
            "vendor gate debug artifact missing",
            artifacts.ArtifactKey.VENDOR_GATE_DEBUG_CSV,
            "Export vendor gate debug CSV from feature build stage.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _check(
            "experiment_registry_exists",
            Path(experiment_registry_path).exists(),
            "fatal",
            "experiment registry missing",
            artifacts.ArtifactKey.EXPERIMENT_REGISTRY_JSON,
            "Ensure registry write in finalize stage.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _check(
            "run_paths_manifest_exists",
            Path(run_paths_manifest_path).exists(),
            "fatal",
            "run paths manifest missing",
            artifacts.ArtifactKey.RUN_PATHS_MANIFEST_JSON,
            "Ensure manifest writer persists run_paths_manifest.",
            enabled=paper_mode,
        )
    )
    checks.append(
        _check(
            "taxonomy_type_audit_not_blind",
            bool(taxonomy_summary_path)
            and Path(taxonomy_summary_path).exists()
            and int(taxonomy_type_rows_evaluated) > 0,
            "fatal",
            f"taxonomy type audit blind or missing (type_rows_evaluated={int(taxonomy_type_rows_evaluated)})",
            artifacts.ArtifactKey.RUN_PATHS_MANIFEST_JSON,
            "Ensure taxonomy audit has type_slug_expected coverage before finalizing paper run.",
            enabled=paper_mode,
        )
    )
    return checks


def _check(
    check_id: str,
    passed: bool,
    severity: str,
    reason: str,
    artifact_key: str,
    remediation: str,
    *,
    enabled: bool,
) -> dict[str, Any]:
    """Build one compliance row."""
    if not enabled:
        return {
            "check_id": check_id,
            "status": "skipped",
            "severity": severity,
            "reason": "paper_mode disabled",
            "artifact_key": artifact_key,
            "remediation": "",
        }
    return {
        "check_id": check_id,
        "status": "pass" if passed else "fail",
        "severity": severity,
        "reason": "" if passed else reason,
        "artifact_key": artifact_key,
        "remediation": "" if passed else remediation,
    }


def _summarize_engine_lifecycle(
    pipeline_results: dict[str, Any] | None,
) -> tuple[int, int, list[str]]:
    """Summarize included/excluded engine counts and canonical names."""
    engine_lifecycle = None
    if isinstance(pipeline_results, dict):
        engine_lifecycle = pipeline_results.get("engine_lifecycle")

    if not isinstance(engine_lifecycle, pd.DataFrame) or engine_lifecycle.empty:
        return 0, 0, []

    included_engines = int(
        engine_lifecycle["included_in_model_flag"].fillna(False).astype(bool).sum()
    )
    excluded_engines = int(
        (~engine_lifecycle["included_in_model_flag"].fillna(False).astype(bool)).sum()
    )
    engine_names = sorted(
        engine_lifecycle["engine_name_canonical"].dropna().astype(str).unique().tolist()
    )
    return included_engines, excluded_engines, engine_names


def _extract_parser_list(vendor_eval_df: pd.DataFrame | None) -> list[str]:
    """Extract sorted parser list from vendor evaluation dataframe."""
    if not isinstance(vendor_eval_df, pd.DataFrame) or "Vendor" not in vendor_eval_df.columns:
        return []
    return sorted(vendor_eval_df["Vendor"].dropna().astype(str).unique().tolist())


def _compute_dataset_hash(samples_df: pd.DataFrame | None) -> str:
    """Compute dataset hash from sorted sample_id values."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty or "sample_id" not in samples_df.columns:
        return ""
    values = samples_df["sample_id"].dropna().tolist()
    return dataset_hash_from_sample_ids(values)


def _rank_tier_from_publication_score(score: float) -> str:
    """Map publication score to fixed PM-approved tiers."""
    if score >= 0.75:
        return "High"
    if score >= 0.25:
        return "Moderate"
    return "Low"


def _export_engine_ranking_tiers(
    *,
    run_root: Path,
    run_id: str,
    evidence_mode: bool,
    weights_df: pd.DataFrame | None,
) -> tuple[Path | None, str]:
    """Export deterministic Paper #2 engine ranking table and hash."""
    if not isinstance(weights_df, pd.DataFrame) or weights_df.empty:
        return None, ""
    if evidence_mode:
        out_dir = run_root / "paper2_pack"
    else:
        out_dir = run_root / "paper_exports" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)

    frame = weights_df.copy()
    vendor_col = "Vendor" if "Vendor" in frame.columns else None
    if vendor_col is None:
        return None, ""
    if "Leakage Safe Score Raw" not in frame.columns:
        return None, ""

    frame["engine_id"] = frame[vendor_col].astype(str).str.strip().str.lower()
    frame["publication_score"] = pd.to_numeric(frame["Leakage Safe Score Raw"], errors="coerce").fillna(0.0)
    rel_col = "Reliability" if "Reliability" in frame.columns else ("Specificity Score" if "Specificity Score" in frame.columns else None)
    if rel_col:
        frame["reliability_score"] = pd.to_numeric(frame[rel_col], errors="coerce").fillna(0.0)
    else:
        frame["reliability_score"] = 0.0
    frame["final_ml_score"] = pd.to_numeric(frame.get("Final ML Score", 0.0), errors="coerce").fillna(0.0)
    frame["composite_score"] = pd.to_numeric(frame.get("Composite Score", 0.0), errors="coerce").fillna(0.0)
    frame["enrichment_score"] = pd.to_numeric(frame.get("Enrichment Score", 0.0), errors="coerce").fillna(0.0)
    frame["parser_gate_status"] = frame.get("parser_gate_status", "unknown").astype(str)
    frame["included_in_model"] = pd.to_numeric(frame.get("included_in_model", 0), errors="coerce").fillna(0).astype(int)
    frame = frame.sort_values(
        ["publication_score", "reliability_score", "engine_id"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    frame["rank"] = frame.index + 1
    frame["tier"] = frame["publication_score"].apply(_rank_tier_from_publication_score)
    columns = [
        "rank",
        "engine_id",
        "publication_score",
        "tier",
        "final_ml_score",
        "reliability_score",
        "composite_score",
        "enrichment_score",
        "parser_gate_status",
        "included_in_model",
    ]
    export_df = frame[columns].copy()
    out_path = out_dir / "engine_ranking_tiers.csv"
    export_df.to_csv(out_path, index=False, lineterminator="\n", float_format="%.6f")
    ranking_hash = sha256_hex(
        canonical_csv_bytes(
            export_df,
            float_format="%.6f",
            lineterminator="\n",
        )
    )
    return out_path, ranking_hash


def _export_parser_quality_final(
    *,
    diagnostics_dir: Path,
    run_id: str,
    weights_df: pd.DataFrame | None,
) -> Path | None:
    """Export final parser-gate/model-inclusion snapshot from engine weights."""
    if not isinstance(weights_df, pd.DataFrame) or weights_df.empty:
        return None
    vendor_col = "Vendor" if "Vendor" in weights_df.columns else None
    if vendor_col is None:
        return None
    frame = weights_df.copy()
    export_df = pd.DataFrame(
        {
            "vendor_id": frame[vendor_col].astype(str).str.strip().str.lower(),
            "parser_gate_status": frame.get("parser_gate_status", "unknown").astype(str),
            "included_in_model": pd.to_numeric(
                frame.get("included_in_model", 0),
                errors="coerce",
            ).fillna(0).astype(int),
            "diagnostic_stage": "engine_weights_final",
        }
    )
    export_df["included_in_engine_weights"] = export_df["included_in_model"].astype(int)
    export_df["selected_for_feature_matrix"] = np.nan
    export_df["selection_status"] = "unknown"
    export_df["selection_stage"] = "feature_matrix_topk"
    debug_path = diagnostics_dir / f"vendor_gate_debug_{run_id}.csv"
    if not debug_path.exists():
        debug_path = diagnostics_dir / "vendor_gate_debug.latest.csv"
    if debug_path.exists():
        try:
            debug_df = pd.read_csv(debug_path)
            if not debug_df.empty and "vendor" in debug_df.columns:
                sel = pd.DataFrame(
                    {
                        "vendor_id": debug_df["vendor"].astype(str).str.strip().str.lower(),
                        "selected_for_feature_matrix": pd.to_numeric(
                            debug_df.get("selected_flag", 0),
                            errors="coerce",
                        ).fillna(0).astype(int),
                    }
                ).drop_duplicates(subset=["vendor_id"], keep="last")
                export_df = export_df.merge(sel, on="vendor_id", how="left", suffixes=("", "_dbg"))
                if "selected_for_feature_matrix_dbg" in export_df.columns:
                    export_df["selected_for_feature_matrix"] = (
                        pd.to_numeric(export_df["selected_for_feature_matrix_dbg"], errors="coerce")
                        .fillna(pd.to_numeric(export_df["selected_for_feature_matrix"], errors="coerce"))
                    )
                    export_df = export_df.drop(columns=["selected_for_feature_matrix_dbg"])
                export_df["selected_for_feature_matrix"] = pd.to_numeric(
                    export_df["selected_for_feature_matrix"],
                    errors="coerce",
                ).fillna(0).astype(int)
                export_df["selection_status"] = export_df["selected_for_feature_matrix"].map(
                    {1: "selected_topk", 0: "not_selected_topk"}
                ).fillna("unknown")
        except Exception:
            pass
    run_path = diagnostics_dir / f"parser_quality_final_{run_id}.csv"
    latest_path = diagnostics_dir / "parser_quality_final.latest.csv"
    export_df.to_csv(run_path, index=False)
    export_df.to_csv(latest_path, index=False)
    return run_path


def _build_paper2_pack(
    *,
    run_root: Path,
    run_id: str,
    samples_df: pd.DataFrame | None,
    manifest: dict[str, Any],
    manifest_context: dict[str, Any],
    ranking_path: Path | None,
) -> dict[str, str]:
    """Build run-scoped Paper #2 artifact pack files."""
    pack_dir = run_root / "paper2_pack"
    pack_dir.mkdir(parents=True, exist_ok=True)
    artifacts_written: dict[str, str] = {}

    sample_count = int(len(samples_df)) if isinstance(samples_df, pd.DataFrame) else 0
    family_counts: dict[str, int] = {}
    max_family_share = 0.0
    if isinstance(samples_df, pd.DataFrame) and "family_canonical" in samples_df.columns:
        counts = (
            samples_df["family_canonical"].fillna("unknown").astype(str).value_counts()
        )
        family_counts = {str(k): int(v) for k, v in counts.to_dict().items()}
        if sample_count > 0 and not counts.empty:
            max_family_share = float(counts.iloc[0] / sample_count)
    dataset_characterization = {
        "run_id": run_id,
        "sample_count": sample_count,
        "family_count": len(family_counts),
        "family_distribution": family_counts,
        "max_family_share": round(max_family_share, 6),
        "unknown_excluded_count": int(manifest_context.get("unknown_excluded_count", 0) or 0),
        "time_window": {
            "start_utc": ((manifest_context.get("profile_params", {}) or {}).get("cohort_gates", {}) or {}).get("time_window_start_utc"),
            "end_utc": ((manifest_context.get("profile_params", {}) or {}).get("cohort_gates", {}) or {}).get("time_window_end_utc"),
        },
        "dataset_hash": manifest.get("dataset_hash", ""),
    }
    dataset_path = pack_dir / "dataset_characterization.json"
    dataset_path.write_text(json.dumps(dataset_characterization, indent=2, sort_keys=True), encoding="utf-8")
    artifacts_written["dataset_characterization.json"] = str(dataset_path)

    if ranking_path is not None and ranking_path.exists():
        artifacts_written["engine_ranking_tiers.csv"] = str(ranking_path)

    consensus_df, consensus_stats = _build_consensus_distribution(samples_df=samples_df, manifest=manifest)
    consensus_csv = pack_dir / "consensus_distribution.csv"
    consensus_df.to_csv(consensus_csv, index=False, lineterminator="\n", float_format="%.6f")
    artifacts_written["consensus_distribution.csv"] = str(consensus_csv)
    consensus_stats_path = pack_dir / "consensus_stats.json"
    consensus_stats_path.write_text(json.dumps(consensus_stats, indent=2, sort_keys=True), encoding="utf-8")
    artifacts_written["consensus_stats.json"] = str(consensus_stats_path)
    consensus_png = pack_dir / "consensus_distribution.png"
    _render_consensus_distribution_png(consensus_df=consensus_df, output_path=consensus_png)
    artifacts_written["consensus_distribution.png"] = str(consensus_png)

    metrics_payload = {
        "run_id": run_id,
        "model_summary": manifest_context.get("model_summary", {}),
    }
    metrics_path = pack_dir / "model_metrics.json"
    metrics_path.write_text(json.dumps(metrics_payload, indent=2, sort_keys=True), encoding="utf-8")
    artifacts_written["model_metrics.json"] = str(metrics_path)

    conf_src = _find_primary_confusion_matrix(
        run_root=run_root,
        top_model=str((manifest_context.get("model_summary") or {}).get("top_model", "")),
        evidence_mode=bool(manifest.get("evidence_mode", False)),
    )
    if conf_src is not None and conf_src.exists():
        conf_dst = pack_dir / "confusion_matrix_primary.png"
        conf_dst.write_bytes(conf_src.read_bytes())
        artifacts_written["confusion_matrix_primary.png"] = str(conf_dst)

    manifest_src = run_root / "run_manifest.json"
    if not manifest_src.exists():
        manifest_src = run_manifest.resolve_manifest_path()
    if manifest_src.exists():
        manifest_dst = pack_dir / "manifest.json"
        manifest_dst.write_bytes(manifest_src.read_bytes())
        artifacts_written["manifest.json"] = str(manifest_dst)

    compliance_path = pack_dir / "evidence_compliance_summary.json"
    compliance_payload = {
        "run_id": run_id,
        "evidence_mode": bool(manifest.get("evidence_mode", False)),
        "non_standard_features": bool(manifest.get("non_standard_features", False)),
        "fallback_used": bool(manifest.get("vendor_fallback_used", False)),
        "requested_top_k": int(manifest.get("k_requested", 0) or 0),
        "effective_top_k": int(manifest.get("effective_top_k", 0) or 0),
    }
    compliance_path.write_text(json.dumps(compliance_payload, indent=2, sort_keys=True), encoding="utf-8")
    artifacts_written["evidence_compliance_summary.json"] = str(compliance_path)
    return artifacts_written


def _build_consensus_distribution(
    *,
    samples_df: pd.DataFrame | None,
    manifest: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build consensus distribution table and summary stats."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        empty = pd.DataFrame(columns=["bucket", "raw_count", "percent"])
        stats = {"sample_count": 0}
        return empty, stats
    mal = pd.to_numeric(samples_df.get("vt_malicious_count", 0), errors="coerce").fillna(0.0)
    susp = pd.to_numeric(samples_df.get("vt_suspicious_count", 0), errors="coerce").fillna(0.0)
    denom = max(int(manifest.get("engine_count_observed", 0) or 0), 1)
    ratio = ((mal + susp) / float(denom)).clip(lower=0.0, upper=1.0)
    bins = pd.cut(
        ratio,
        bins=[-0.001, 0.1, 0.25, 0.5, 0.75, 1.0],
        labels=["0-0.10", "0.10-0.25", "0.25-0.50", "0.50-0.75", "0.75-1.00"],
        include_lowest=True,
    )
    table = (
        bins.value_counts(sort=False)
        .rename_axis("bucket")
        .reset_index(name="raw_count")
    )
    table["percent"] = (table["raw_count"] / max(len(ratio), 1)).round(6)
    stats = {
        "sample_count": int(len(ratio)),
        "min": round(float(ratio.min()), 6),
        "max": round(float(ratio.max()), 6),
        "mean": round(float(ratio.mean()), 6),
        "median": round(float(ratio.median()), 6),
        "std": round(float(ratio.std(ddof=0)), 6),
        "q1": round(float(ratio.quantile(0.25)), 6),
        "q3": round(float(ratio.quantile(0.75)), 6),
    }
    return table, stats


def _render_consensus_distribution_png(*, consensus_df: pd.DataFrame, output_path: Path) -> None:
    """Render consensus distribution bar chart."""
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception:
        return
    fig, ax = plt.subplots(figsize=(7.16, 3.4))
    ax.bar(consensus_df["bucket"].astype(str), pd.to_numeric(consensus_df["percent"], errors="coerce").fillna(0.0))
    ax.set_ylabel("Percent")
    ax.set_xlabel("Consensus Score Bucket")
    ax.set_title("Consensus Distribution")
    ax.set_ylim(0, 1.0)
    ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def _find_primary_confusion_matrix(*, run_root: Path, top_model: str, evidence_mode: bool = False) -> Path | None:
    """Resolve primary confusion matrix path from run-scoped output."""
    cm_dir = run_root / "conf_matrices"
    if not cm_dir.exists():
        return None
    if evidence_mode:
        rf_candidate = cm_dir / "confusion_matrix_random_forest.png"
        if rf_candidate.exists():
            return rf_candidate
        rf_suffix = list(cm_dir.glob("confusion_matrix_*random_forest*.png"))
        if rf_suffix:
            return sorted(rf_suffix)[0]
    candidate = cm_dir / f"confusion_matrix_{top_model}.png"
    if candidate.exists():
        return candidate
    with_suffix = list(cm_dir.glob(f"confusion_matrix_*{top_model}.png"))
    if with_suffix:
        return sorted(with_suffix)[0]
    files = sorted(cm_dir.glob("confusion_matrix_*.png"))
    return files[0] if files else None


def _export_trained_family_registry(
    *,
    samples_df: pd.DataFrame | None,
    run_id: str,
    diagnostics_dir: Path,
) -> tuple[Path | None, int]:
    """Export family inclusion table after min-support filtering policy."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return None, 0
    if "family_canonical" not in samples_df.columns:
        return None, 0
    min_support = int(
        getattr(
            app_config,
            "RUNTIME_MIN_FAMILY_SUPPORT",
            getattr(app_config, "MIN_FAMILY_SUPPORT", 3),
        )
        or 3
    )
    frame = samples_df.copy()
    frame["family_canonical"] = frame["family_canonical"].fillna("").astype(str).str.strip()
    frame["type_slug"] = frame.get("type_slug", "").fillna("").astype(str).str.strip().str.lower()
    frame = frame[frame["family_canonical"] != ""].copy()
    if frame.empty:
        return None, 0
    grouped = (
        frame.groupby(["family_canonical", "type_slug"], as_index=False)
        .size()
        .rename(columns={"size": "sample_count"})
        .sort_values(
            by=["sample_count", "family_canonical", "type_slug"],
            ascending=[False, True, True],
            kind="mergesort",
        )
    )
    dedup = grouped.drop_duplicates(subset=["family_canonical"], keep="first").copy()
    dedup["included_in_training"] = (
        pd.to_numeric(dedup["sample_count"], errors="coerce").fillna(0).astype(int) >= max(min_support, 1)
    ).astype(int)
    dedup = dedup.sort_values(
        by=["sample_count", "family_canonical"],
        ascending=[False, True],
        kind="mergesort",
    )
    out_df = dedup[["family_canonical", "type_slug", "sample_count", "included_in_training"]].copy()
    out_df.insert(0, "run_id", str(run_id))
    run_path = diagnostics_dir / f"trained_family_registry_{run_id}.csv"
    latest_path = diagnostics_dir / "trained_family_registry.latest.csv"
    out_df.to_csv(run_path, index=False)
    out_df.to_csv(latest_path, index=False)
    included = int(out_df["included_in_training"].sum())
    return run_path, included


def _export_confusion_matrix_provenance(
    *,
    run_root: Path,
    run_id: str,
    diagnostics_dir: Path,
    manifest_context: dict[str, Any],
    trained_family_count: int,
    evidence_mode: bool,
) -> Path | None:
    """Export explicit confusion matrix provenance for paper traceability."""
    model_name = "random_forest"
    conf_path = _find_primary_confusion_matrix(
        run_root=run_root,
        top_model=model_name,
        evidence_mode=True if evidence_mode else False,
    )
    if conf_path is None or not conf_path.exists():
        return None

    test_samples = 0
    model_meta_path = run_root / "models" / model_name / f"{model_name}_classifier_model_metadata.json"
    if model_meta_path.exists():
        try:
            payload = json.loads(model_meta_path.read_text(encoding="utf-8"))
            evaluation = payload.get("evaluation", {}) if isinstance(payload, dict) else {}
            test_samples = int(evaluation.get("samples_tested", 0) or 0)
        except Exception:
            test_samples = 0

    provenance_df = pd.DataFrame(
        [
            {
                "run_id": str(run_id),
                "model_name": model_name,
                "eval_source": "test_set",
                "test_sample_count": int(test_samples),
                "trained_family_count": int(trained_family_count),
                "confusion_matrix_path": str(conf_path.resolve()),
            }
        ]
    )
    run_path = diagnostics_dir / f"confusion_matrix_provenance_{run_id}.csv"
    latest_path = diagnostics_dir / "confusion_matrix_provenance.latest.csv"
    provenance_df.to_csv(run_path, index=False)
    provenance_df.to_csv(latest_path, index=False)
    return run_path


def _build_cohort_limitation_summary(samples_df: pd.DataFrame | None) -> dict[str, Any]:
    """Build compact cohort limitation summary for methods/discussion sections."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return {
            "total_samples": 0,
            "total_cohort_families": 0,
            "training_families": 0,
            "represented_types": 0,
            "top_family_share": 0.0,
            "banker_share": 0.0,
        }
    sample_count = int(len(samples_df))
    family_series = samples_df.get("family_canonical", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    family_counts = family_series[family_series != ""].value_counts()
    type_series = samples_df.get("type_slug", pd.Series(dtype=str)).fillna("").astype(str).str.strip().str.lower()
    type_counts = type_series[type_series != ""].value_counts()
    min_support = int(
        getattr(
            app_config,
            "RUNTIME_MIN_FAMILY_SUPPORT",
            getattr(app_config, "MIN_FAMILY_SUPPORT", 3),
        )
        or 3
    )
    training_families = int((family_counts >= max(min_support, 1)).sum()) if not family_counts.empty else 0
    top_family_share = float((family_counts.iloc[0] / sample_count) if sample_count > 0 and not family_counts.empty else 0.0)
    banker_share = float((type_counts.get("banker", 0) / sample_count) if sample_count > 0 else 0.0)
    return {
        "total_samples": sample_count,
        "total_cohort_families": int(family_counts.shape[0]),
        "training_families": training_families,
        "represented_types": int(type_counts.shape[0]),
        "top_family_share": round(top_family_share, 6),
        "banker_share": round(banker_share, 6),
    }


def _build_strict_paper2_exports(
    *,
    run_root: Path,
    diagnostics_dir: Path,
    run_id: str,
    samples_df: pd.DataFrame | None,
    manifest_context: dict[str, Any],
    evidence_mode: bool,
    paper_mode: bool,
) -> dict[str, Any]:
    """Build strict Paper #2 export set and fail on missing locked artifacts."""
    paper_exports_root = run_root / "paper_exports"
    if not bool(paper_mode):
        if paper_exports_root.exists():
            shutil.rmtree(paper_exports_root)
            du.print_info("[PAPER2] Removed stale paper_exports (paper mode OFF).")
        du.print_info("[PAPER2] Strict paper export skipped (paper mode OFF).")
        return {
            "profile": {
                "enabled": False,
                "reason": "paper_mode_disabled",
                "single_run_id": str(run_id),
            },
            "artifact_paths": [],
        }
    strict_profile = bool(getattr(app_config, "PAPER2_STRICT_EXPORT_PROFILE", True)) and bool(paper_mode)
    contract_version = "paper2.v2"
    temp_export_root = run_root / f"paper_exports.__tmp__{uuid4().hex[:8]}"
    if temp_export_root.exists():
        shutil.rmtree(temp_export_root, ignore_errors=True)

    required_figure_ids = {
        "fig1_pipeline_architecture",
        "fig2_type_permission_heatmap",
        "fig3_dangerous_permission_distribution_by_type",
        "fig4_family_jsd_heatmap_top12",
        "fig5_confusion_matrix_random_forest",
    }
    required_table_ids = {
        "table1_cohort_summary",
        "table2_malware_family_temporal_scope",
        "table3_model_comparison_rf_xgb_lr_fused",
        "table4_feature_ablation",
        "table5_dangerous_permission_stats_tests",
    }
    blocked_non_paper_ids = {
        "family_permission_heatmap_top12",
        "generic_consensus_vs_entropy",
        "per_family_performance_spread",
        "misclassified_samples_by_type",
    }

    figure_filename_map = {
        "fig1_pipeline_architecture": "pipeline_architecture.png",
        "fig2_type_permission_heatmap": "type_permission_heatmap.png",
        "fig3_dangerous_permission_distribution_by_type": "dangerous_permission_distribution_by_type.png",
        "fig4_family_jsd_heatmap_top12": "family_jsd_heatmap_top12.png",
        "fig5_confusion_matrix_random_forest": "confusion_matrix_random_forest.png",
    }
    table_filename_map = {
        "table1_cohort_summary": "cohort_summary.csv",
        "table2_malware_family_temporal_scope": "malware_family_temporal_scope.csv",
        "table3_model_comparison_rf_xgb_lr_fused": "model_comparison_rf_xgb_lr_fused.csv",
        "table4_feature_ablation": "feature_ablation.csv",
        "table5_dangerous_permission_stats_tests": "dangerous_permission_stats_tests.csv",
    }

    bundle_dir = run_root / "bundles" / "permission_trends"
    figure_sources: dict[str, Path] = {}
    conf_rf = _find_primary_confusion_matrix(
        run_root=run_root,
        top_model="random_forest",
        evidence_mode=True if evidence_mode else False,
    )
    if conf_rf is not None:
        figure_sources["fig5_confusion_matrix_random_forest"] = conf_rf

    table_sources = {
        "table3_model_comparison_rf_xgb_lr_fused": diagnostics_dir / f"model_comparison_summary_{run_id}.csv",
        "table4_feature_ablation": diagnostics_dir / "ablation_summary.csv",
        "table5_dangerous_permission_stats_tests": bundle_dir / "tables" / "dangerous_stats_tests.latest.csv",
    }
    figure_stage_map = {
        "fig1_pipeline_architecture": "manifest_export",
        "fig2_type_permission_heatmap": "permission_trends_bundle.tables",
        "fig3_dangerous_permission_distribution_by_type": "permission_trends_bundle.tables",
        "fig4_family_jsd_heatmap_top12": "diagnostics.family_jsd_pairs_verification",
        "fig5_confusion_matrix_random_forest": "training_evaluation.conf_matrices",
    }
    table_stage_map = {
        "table1_cohort_summary": "manifest_export.samples",
        "table2_malware_family_temporal_scope": "manifest_export.samples",
        "table3_model_comparison_rf_xgb_lr_fused": "training_summary.diagnostics",
        "table4_feature_ablation": "ablation.diagnostics",
        "table5_dangerous_permission_stats_tests": "permission_trends_bundle.tables",
    }

    type_prev_csv = bundle_dir / "tables" / "type_permission_prevalence.latest.csv"
    discrim_csv = bundle_dir / "tables" / "permission_discriminability_rank.latest.csv"
    dangerous_csv = bundle_dir / "tables" / "dangerous_distribution_by_type.latest.csv"
    jsd_pairs_csv = diagnostics_dir / f"family_jsd_pairs_verification_{run_id}.csv"

    required_sources: dict[str, Path] = {
        "fig2_type_permission_heatmap:table_type_permission_prevalence": type_prev_csv,
        "fig2_type_permission_heatmap:table_permission_discriminability_rank": discrim_csv,
        "fig3_dangerous_permission_distribution_by_type:table_dangerous_distribution": dangerous_csv,
        "fig4_family_jsd_heatmap_top12:table_jsd_pairs_verification": jsd_pairs_csv,
        "fig5_confusion_matrix_random_forest:figure_confusion_matrix": (
            conf_rf if conf_rf is not None else (run_root / "__missing_confusion_matrix__")
        ),
        "table3_model_comparison_rf_xgb_lr_fused:source_model_comparison": table_sources[
            "table3_model_comparison_rf_xgb_lr_fused"
        ],
        "table4_feature_ablation:source_ablation_summary": table_sources["table4_feature_ablation"],
        "table5_dangerous_permission_stats_tests:source_dangerous_stats": table_sources[
            "table5_dangerous_permission_stats_tests"
        ],
    }

    missing: list[str] = []
    for logical, path in required_sources.items():
        if path is None or not Path(path).exists():
            missing.append(logical)
    if missing and strict_profile:
        raise ValueError(
            "[PAPER2] Strict paper export failed; missing required artifacts: "
            + ", ".join(sorted(missing))
        )
    exported_paths: list[str] = []
    figure_registry_rows: list[dict[str, Any]] = []
    table_registry_rows: list[dict[str, Any]] = []
    figure_inputs: dict[str, list[str]] = {}
    table_inputs: dict[str, list[str]] = {}
    validation_summary: dict[str, Any] = {}
    try:
        fig_dir = temp_export_root / "figures"
        tab_dir = temp_export_root / "tables"
        latex_dir = temp_export_root / "tables_latex"
        docs_dir = temp_export_root / "docs"
        fig_dir.mkdir(parents=True, exist_ok=True)
        tab_dir.mkdir(parents=True, exist_ok=True)
        latex_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.mkdir(parents=True, exist_ok=True)

        # Figure 1: deterministic pipeline architecture figure generated for paper exports.
        fig1_id = "fig1_pipeline_architecture"
        fig1_path = fig_dir / figure_filename_map[fig1_id]
        _render_pipeline_architecture_figure(output_path=fig1_path)
        exported_paths.append(str(fig1_path))
        figure_registry_rows.append(
            {
                "run_id": str(run_id),
                "contract_version": contract_version,
                "figure_id": fig1_id,
                "destination_filename": fig1_path.name,
                "destination_path": str((run_root / "paper_exports" / "figures" / fig1_path.name).resolve()),
                "source_path": "",
                "source_stage": figure_stage_map.get(fig1_id, "unknown"),
                "qc_status": "pass",
                "notes": "generated",
            }
        )
        figure_inputs[fig1_id] = []

        for figure_id, src in figure_sources.items():
            src_path = Path(src)
            if not src_path.exists():
                continue
            if run_root.resolve() not in src_path.resolve().parents:
                raise ValueError(f"[PAPER2] Non run-scoped source rejected: {src_path}")
            dst = fig_dir / figure_filename_map[figure_id]
            shutil.copy2(src_path, dst)
            exported_paths.append(str(dst))
            figure_registry_rows.append(
                {
                    "run_id": str(run_id),
                    "contract_version": contract_version,
                    "figure_id": figure_id,
                    "destination_filename": dst.name,
                    "destination_path": str((run_root / "paper_exports" / "figures" / dst.name).resolve()),
                    "source_path": str(src_path.resolve()),
                    "source_stage": figure_stage_map.get(figure_id, "unknown"),
                    "qc_status": "pass",
                    "notes": "copied",
                }
            )
            figure_inputs[figure_id] = [str(src_path.resolve())]

        conf_dst = fig_dir / figure_filename_map["fig5_confusion_matrix_random_forest"]
        _annotate_confusion_matrix_with_metrics(
            confusion_path=conf_dst,
            model_comparison_csv=diagnostics_dir / f"model_comparison_summary_{run_id}.csv",
        )

        # Re-render key paper figures from run-scoped tables for publication readability.
        _render_paper_type_heatmap_from_table(
            type_prevalence_path=type_prev_csv,
            discriminability_path=discrim_csv,
            output_path=fig_dir / figure_filename_map["fig2_type_permission_heatmap"],
            top_permissions=int(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 16)),
        )
        _render_paper_dangerous_distribution_from_table(
            dangerous_distribution_path=dangerous_csv,
            output_path=fig_dir / figure_filename_map["fig3_dangerous_permission_distribution_by_type"],
        )
        _render_paper_jsd_heatmap_from_pairs(
            jsd_pair_path=jsd_pairs_csv,
            output_path=fig_dir / figure_filename_map["fig4_family_jsd_heatmap_top12"],
        )
        for figure_id, source_paths in {
            "fig2_type_permission_heatmap": [type_prev_csv, discrim_csv],
            "fig3_dangerous_permission_distribution_by_type": [dangerous_csv],
            "fig4_family_jsd_heatmap_top12": [jsd_pairs_csv],
        }.items():
            rendered_dst = fig_dir / figure_filename_map[figure_id]
            figure_registry_rows.append(
                {
                    "run_id": str(run_id),
                    "contract_version": contract_version,
                    "figure_id": figure_id,
                    "destination_filename": rendered_dst.name,
                    "destination_path": str((run_root / "paper_exports" / "figures" / rendered_dst.name).resolve()),
                    "source_path": ";".join([str(Path(p).resolve()) for p in source_paths]),
                    "source_stage": figure_stage_map.get(figure_id, "unknown"),
                    "qc_status": "pass",
                    "notes": "rendered_from_tables",
                }
            )
            if str(rendered_dst) not in exported_paths:
                exported_paths.append(str(rendered_dst))
        figure_inputs["fig2_type_permission_heatmap"] = [str(type_prev_csv.resolve()), str(discrim_csv.resolve())]
        figure_inputs["fig3_dangerous_permission_distribution_by_type"] = [str(dangerous_csv.resolve())]
        figure_inputs["fig4_family_jsd_heatmap_top12"] = [str(jsd_pairs_csv.resolve())]

        cohort_id = "table1_cohort_summary"
        cohort_summary_path = tab_dir / table_filename_map[cohort_id]
        cohort_summary_df = _build_paper_cohort_summary_table(samples_df=samples_df, run_id=run_id)
        cohort_summary_df.to_csv(cohort_summary_path, index=False)
        exported_paths.append(str(cohort_summary_path))
        table_registry_rows.append(
            {
                "run_id": str(run_id),
                "contract_version": contract_version,
                "table_id": cohort_id,
                "destination_filename": cohort_summary_path.name,
                "destination_path": str((run_root / "paper_exports" / "tables" / cohort_summary_path.name).resolve()),
                "source_path": "",
                "source_stage": table_stage_map.get(cohort_id, "unknown"),
                "qc_status": "pass",
                "notes": "generated",
            }
        )
        table_inputs[cohort_id] = []

        temporal_id = "table2_malware_family_temporal_scope"
        temporal_path = tab_dir / table_filename_map[temporal_id]
        temporal_df = _build_family_temporal_scope_table(samples_df=samples_df, run_id=run_id)
        temporal_df.to_csv(temporal_path, index=False)
        exported_paths.append(str(temporal_path))
        table_registry_rows.append(
            {
                "run_id": str(run_id),
                "contract_version": contract_version,
                "table_id": temporal_id,
                "destination_filename": temporal_path.name,
                "destination_path": str((run_root / "paper_exports" / "tables" / temporal_path.name).resolve()),
                "source_path": "",
                "source_stage": table_stage_map.get(temporal_id, "unknown"),
                "qc_status": "pass",
                "notes": "generated",
            }
        )
        table_inputs[temporal_id] = []

        temporal_provenance_path = docs_dir / "temporal_timestamp_provenance.json"
        temporal_provenance_payload = {
            "run_id": str(run_id),
            "timestamp_field": "effective_first_seen_at_utc",
            "timestamp_priority_chain": [
                "effective_first_seen_at_utc",
                "vt_first_seen_itw_date",
                "vt_first_submission_at_utc",
            ],
            "source_contract_path": str(diagnostics_dir / "dataset_time_contract.latest.json"),
        }
        temporal_provenance_path.write_text(
            json.dumps(temporal_provenance_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        exported_paths.append(str(temporal_provenance_path))

        for table_id, src in table_sources.items():
            src_path = Path(src)
            if not src_path.exists():
                continue
            if run_root.resolve() not in src_path.resolve().parents:
                raise ValueError(f"[PAPER2] Non run-scoped source rejected: {src_path}")
            dst = tab_dir / table_filename_map[table_id]
            if table_id == "table3_model_comparison_rf_xgb_lr_fused":
                _build_paper_model_comparison_table(source_path=src_path, output_path=dst)
            elif table_id == "table4_feature_ablation":
                _build_paper_ablation_table(source_path=src_path, output_path=dst)
            else:
                shutil.copy2(src_path, dst)
            exported_paths.append(str(dst))
            table_registry_rows.append(
                {
                    "run_id": str(run_id),
                    "contract_version": contract_version,
                    "table_id": table_id,
                    "destination_filename": dst.name,
                    "destination_path": str((run_root / "paper_exports" / "tables" / dst.name).resolve()),
                    "source_path": str(src_path.resolve()),
                    "source_stage": table_stage_map.get(table_id, "unknown"),
                    "qc_status": "pass",
                    "notes": "generated_from_source" if table_id != "table5_dangerous_permission_stats_tests" else "copied",
                }
            )
            table_inputs[table_id] = [str(src_path.resolve())]

        seen_figures = {str(row.get("figure_id", "")) for row in figure_registry_rows}
        seen_tables = {str(row.get("table_id", "")) for row in table_registry_rows}
        if strict_profile and (seen_figures != required_figure_ids or seen_tables != required_table_ids):
            missing_figures = sorted(required_figure_ids - seen_figures)
            extra_figures = sorted(seen_figures - required_figure_ids)
            missing_tables = sorted(required_table_ids - seen_tables)
            extra_tables = sorted(seen_tables - required_table_ids)
            raise ValueError(
                "[PAPER2] Strict export contract violation: "
                f"missing_figures={missing_figures}, extra_figures={extra_figures}, "
                f"missing_tables={missing_tables}, extra_tables={extra_tables}"
            )

        validation_summary = _validate_paper_export_content(
            run_id=run_id,
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            fig_dir=fig_dir,
            tab_dir=tab_dir,
            top_permissions=int(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 16)),
            top_families=int(getattr(app_config, "MAX_FAMILY_VISUAL_COUNT", 12)),
            min_family_support=int(getattr(app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 20)),
            strict_profile=strict_profile,
        )

        figure_registry_path = docs_dir / "paper_figure_registry.csv"
        pd.DataFrame(figure_registry_rows).to_csv(figure_registry_path, index=False)
        exported_paths.append(str(figure_registry_path))

        table_registry_path = docs_dir / "paper_table_registry.csv"
        pd.DataFrame(table_registry_rows).to_csv(table_registry_path, index=False)
        exported_paths.append(str(table_registry_path))

        latex_paths: dict[str, str] = {}
        for table_id in sorted(required_table_ids):
            csv_name = table_filename_map[table_id]
            csv_path = tab_dir / csv_name
            tex_path = latex_dir / f"{Path(csv_name).stem}.tex"
            _write_table_latex_from_csv(csv_path=csv_path, tex_path=tex_path)
            exported_paths.append(str(tex_path))
            latex_paths[table_id] = tex_path.name

        profile_payload = {
            "strict_profile_enabled": strict_profile,
            "single_run_id": str(run_id),
            "visual_family_support_threshold": int(getattr(app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 20)),
            "top_families_visual": int(getattr(app_config, "MAX_FAMILY_VISUAL_COUNT", 12)),
            "top_permissions": int(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 16)),
            "paper_export_contract_version": contract_version,
        }
        profile_path = docs_dir / "paper_export_profile.json"
        profile_path.write_text(json.dumps(profile_payload, indent=2, sort_keys=True), encoding="utf-8")
        exported_paths.append(str(profile_path))

        figure_qc_path = docs_dir / "paper_figure_qc.csv"
        _export_paper_figure_qc(fig_dir=fig_dir, output_path=figure_qc_path)
        exported_paths.append(str(figure_qc_path))

        paper_registry_path = docs_dir / "paper_registry.json"
        paper_registry_payload = _build_paper_registry_payload(
            run_root=run_root,
            run_id=run_id,
            contract_version=contract_version,
            figure_registry_rows=figure_registry_rows,
            table_registry_rows=table_registry_rows,
            latex_paths=latex_paths,
            blocked_non_paper_ids=blocked_non_paper_ids,
        )
        paper_registry_path.write_text(
            json.dumps(paper_registry_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        exported_paths.append(str(paper_registry_path))

        export_manifest_path = docs_dir / "paper_exports_manifest.json"
        export_manifest_payload = {
            "run_id": str(run_id),
            "contract_version": contract_version,
            "strict_profile_enabled": bool(strict_profile),
            "run_mode": "paper",
            "figure_ids": sorted([str(row.get("figure_id", "")) for row in figure_registry_rows]),
            "table_ids": sorted([str(row.get("table_id", "")) for row in table_registry_rows]),
            "figure_registry_csv": str(figure_registry_path.resolve()),
            "table_registry_csv": str(table_registry_path.resolve()),
            "paper_export_profile_json": str(profile_path.resolve()),
            "paper_registry_json": str(paper_registry_path.resolve()),
            "tables_latex_dir": str(latex_dir.resolve()),
            "figure_sources": figure_inputs,
            "table_sources": table_inputs,
            "validation_summary": validation_summary,
        }
        export_manifest_path.write_text(
            json.dumps(export_manifest_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        exported_paths.append(str(export_manifest_path))

        if paper_exports_root.exists():
            shutil.rmtree(paper_exports_root)
        temp_export_root.replace(paper_exports_root)
    except Exception:
        if temp_export_root.exists():
            shutil.rmtree(temp_export_root, ignore_errors=True)
        if paper_exports_root.exists():
            shutil.rmtree(paper_exports_root, ignore_errors=True)
        raise

    return {
        "profile": {
            "strict_profile_enabled": strict_profile,
            "single_run_id": str(run_id),
            "visual_family_support_threshold": int(getattr(app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 20)),
            "top_families_visual": int(getattr(app_config, "MAX_FAMILY_VISUAL_COUNT", 12)),
            "top_permissions": int(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 16)),
            "paper_export_contract_version": contract_version,
        },
        "artifact_paths": sorted(set([str(Path(path).resolve()) for path in exported_paths])),
    }


def _build_paper_model_comparison_table(*, source_path: Path, output_path: Path) -> None:
    """Build compact paper model-comparison table for RF/XGB/LR only."""
    src_df = pd.read_csv(source_path)
    if src_df.empty:
        pd.DataFrame(columns=["model", "macro_f1", "accuracy"]).to_csv(output_path, index=False)
        return
    model_col = "Model" if "Model" in src_df.columns else ("model" if "model" in src_df.columns else "")
    macro_col = (
        "MacroF1"
        if "MacroF1" in src_df.columns
        else (
            "Macro F1-Score"
            if "Macro F1-Score" in src_df.columns
            else ("macro_f1" if "macro_f1" in src_df.columns else "")
        )
    )
    acc_col = (
        "Acc"
        if "Acc" in src_df.columns
        else ("Accuracy" if "Accuracy" in src_df.columns else ("accuracy" if "accuracy" in src_df.columns else ""))
    )
    if not model_col or not macro_col or not acc_col:
        src_df.to_csv(output_path, index=False)
        return
    keep_map = {
        "rf": "random_forest",
        "random_forest": "random_forest",
        "xgb": "xgboost",
        "xgboost": "xgboost",
        "log_reg": "logistic_regression",
        "logistic_regression": "logistic_regression",
    }
    work = src_df[[model_col, macro_col, acc_col]].copy()
    work["model"] = work[model_col].astype(str).str.strip().str.lower().map(keep_map)
    work = work[work["model"].isin({"random_forest", "xgboost", "logistic_regression"})].copy()
    work["macro_f1"] = pd.to_numeric(work[macro_col], errors="coerce")
    work["accuracy"] = pd.to_numeric(work[acc_col], errors="coerce")
    order = {"random_forest": 0, "xgboost": 1, "logistic_regression": 2}
    work["order"] = work["model"].map(order).fillna(99).astype(int)
    out = (
        work.sort_values(by=["order", "model"], ascending=[True, True], kind="mergesort")
        .drop_duplicates(subset=["model"], keep="first")
        [["model", "macro_f1", "accuracy"]]
    )
    out.to_csv(output_path, index=False, float_format="%.6f")


def _latex_escape(value: Any) -> str:
    """Escape text for safe LaTeX table rendering."""
    text = "" if value is None else str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    for token, repl in replacements.items():
        text = text.replace(token, repl)
    return text


def _write_table_latex_from_csv(*, csv_path: Path, tex_path: Path) -> None:
    """Render a compact LaTeX tabular from a CSV table."""
    df = pd.read_csv(csv_path)
    columns = [str(col) for col in df.columns.tolist()]
    align = "l" + "r" * max(len(columns) - 1, 0)
    lines: list[str] = []
    lines.append(r"\begin{tabular}{" + align + "}")
    lines.append(r"\hline")
    lines.append(" & ".join(_latex_escape(col) for col in columns) + r" \\")
    lines.append(r"\hline")
    for _, row in df.iterrows():
        cells = [_latex_escape(row[col]) for col in columns]
        lines.append(" & ".join(cells) + r" \\")
    lines.append(r"\hline")
    lines.append(r"\end{tabular}")
    tex_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_paper_registry_payload(
    *,
    run_root: Path,
    run_id: str,
    contract_version: str,
    figure_registry_rows: list[dict[str, Any]],
    table_registry_rows: list[dict[str, Any]],
    latex_paths: dict[str, str],
    blocked_non_paper_ids: set[str],
) -> dict[str, Any]:
    """Build unified paper artifact registry for deterministic manuscript mapping."""
    artifacts_out: list[dict[str, Any]] = []
    for row in figure_registry_rows:
        artifact_id = str(row.get("figure_id", "")).strip()
        temp_destination_path = str(row.get("destination_path", "")).strip()
        destination_filename = str(row.get("destination_filename", "")).strip()
        destination_path = (
            str((run_root / "paper_exports" / "figures" / destination_filename).resolve())
            if destination_filename
            else ""
        )
        source_path = str(row.get("source_path", "")).strip()
        sha = (
            sha256_hex(Path(temp_destination_path).read_bytes())
            if temp_destination_path and Path(temp_destination_path).exists()
            else ""
        )
        artifacts_out.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": "figure",
                "run_id": str(run_id),
                "source_path": source_path,
                "destination_path": destination_path,
                "sha256": sha,
                "paper_allowed": True,
                "contract_version": str(contract_version),
            }
        )
    for row in table_registry_rows:
        artifact_id = str(row.get("table_id", "")).strip()
        temp_destination_path = str(row.get("destination_path", "")).strip()
        destination_filename = str(row.get("destination_filename", "")).strip()
        destination_path = (
            str((run_root / "paper_exports" / "tables" / destination_filename).resolve())
            if destination_filename
            else ""
        )
        source_path = str(row.get("source_path", "")).strip()
        sha = (
            sha256_hex(Path(temp_destination_path).read_bytes())
            if temp_destination_path and Path(temp_destination_path).exists()
            else ""
        )
        latex_name = str(latex_paths.get(artifact_id, "")).strip()
        artifacts_out.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": "table",
                "run_id": str(run_id),
                "source_path": source_path,
                "destination_path": destination_path,
                "sha256": sha,
                "paper_allowed": True,
                "contract_version": str(contract_version),
                "latex_path": (
                    str((run_root / "paper_exports" / "tables_latex" / latex_name).resolve())
                    if latex_name
                    else ""
                ),
            }
        )
    for blocked_id in sorted(blocked_non_paper_ids):
        artifacts_out.append(
            {
                "artifact_id": blocked_id,
                "artifact_type": "blocked_non_paper",
                "run_id": str(run_id),
                "source_path": "",
                "destination_path": "",
                "sha256": "",
                "paper_allowed": False,
                "contract_version": str(contract_version),
            }
        )
    return {
        "run_id": str(run_id),
        "contract_version": str(contract_version),
        "artifacts": sorted(artifacts_out, key=lambda item: str(item.get("artifact_id", ""))),
    }


def _validate_paper_export_content(
    *,
    run_id: str,
    run_root: Path,
    diagnostics_dir: Path,
    fig_dir: Path,
    tab_dir: Path,
    top_permissions: int,
    top_families: int,
    min_family_support: int,
    strict_profile: bool,
) -> dict[str, Any]:
    """Validate paper-export artifact shape/content invariants.

    Raises:
        ValueError: If strict mode is enabled and any invariant fails.
    """
    checks: dict[str, Any] = {
        "figures_png_count": 0,
        "tables_csv_count": 0,
        "model_rows": 0,
        "model_set_ok": False,
        "ablation_feature_set_ok": False,
        "temporal_year_scope_ok": False,
        "dangerous_stats_schema_ok": False,
        "jsd_pair_rows": 0,
        "jsd_family_count": 0,
        "selected_visual_family_count": 0,
        "selected_visual_family_support_floor_ok": False,
        "trained_family_support_floor_ok": False,
        "confusion_eval_source_ok": False,
        "confusion_model_ok": False,
        "top_permissions_requested": int(top_permissions),
        "top_families_requested": int(top_families),
        "min_family_support_required": int(min_family_support),
    }

    fig_files = sorted(fig_dir.glob("*.png"))
    tab_files = sorted(tab_dir.glob("*.csv"))
    checks["figures_png_count"] = int(len(fig_files))
    checks["tables_csv_count"] = int(len(tab_files))
    checks["figures_nonzero_ok"] = bool(all(p.exists() and p.stat().st_size > 0 for p in fig_files))
    checks["tables_nonzero_ok"] = bool(all(p.exists() and p.stat().st_size > 0 for p in tab_files))

    model_path = tab_dir / "model_comparison_rf_xgb_lr_fused.csv"
    if model_path.exists():
        model_df = pd.read_csv(model_path)
        checks["model_rows"] = int(len(model_df))
        if not model_df.empty and {"model", "macro_f1", "accuracy"}.issubset(model_df.columns):
            model_set = set(model_df["model"].astype(str).tolist())
            checks["model_set_ok"] = bool(
                model_set == {"random_forest", "xgboost", "logistic_regression"}
                and len(model_df) == 3
            )

    ablation_path = tab_dir / "feature_ablation.csv"
    if ablation_path.exists():
        abl_df = pd.read_csv(ablation_path)
        if not abl_df.empty and {"feature_set", "model"}.issubset(abl_df.columns):
            feature_set = set(abl_df["feature_set"].astype(str).tolist())
            model_set = set(abl_df["model"].astype(str).tolist())
            checks["ablation_feature_set_ok"] = bool(
                feature_set == {"permissions_only", "vendor_only", "vendor_permissions_fused"}
                and model_set.issubset({"random_forest", "xgboost", "logistic_regression"})
                and len(model_set) > 0
            )

    temporal_path = tab_dir / "malware_family_temporal_scope.csv"
    if temporal_path.exists():
        temp_df = pd.read_csv(temporal_path)
        if not temp_df.empty and {"first_seen", "last_seen"}.issubset(temp_df.columns):
            years = pd.concat(
                [
                    pd.to_datetime(temp_df["first_seen"], errors="coerce", utc=True).dt.year,
                    pd.to_datetime(temp_df["last_seen"], errors="coerce", utc=True).dt.year,
                ],
                ignore_index=True,
            )
            years = years.dropna().astype(int)
            if years.empty:
                checks["temporal_year_scope_ok"] = True
            else:
                checks["temporal_year_scope_ok"] = bool(((years >= 2020) & (years <= 2025)).all())

    dangerous_path = tab_dir / "dangerous_permission_stats_tests.csv"
    if dangerous_path.exists():
        dangerous_df = pd.read_csv(dangerous_path)
        checks["dangerous_stats_schema_ok"] = bool(
            not dangerous_df.empty
            and "metric" in dangerous_df.columns
            and (
                "p_value" in dangerous_df.columns
                or "pvalue" in dangerous_df.columns
                or "p-value" in dangerous_df.columns
            )
        )

    jsd_pairs_path = diagnostics_dir / f"family_jsd_pairs_verification_{run_id}.csv"
    if jsd_pairs_path.exists():
        jsd_df = pd.read_csv(jsd_pairs_path)
        checks["jsd_pair_rows"] = int(len(jsd_df))
        if {"family_a", "family_b"}.issubset(jsd_df.columns):
            fams = set(jsd_df["family_a"].astype(str).tolist()) | set(jsd_df["family_b"].astype(str).tolist())
            checks["jsd_family_count"] = int(len([f for f in fams if str(f).strip()]))

    selected_path = diagnostics_dir / f"selected_families_visual_{run_id}.csv"
    if selected_path.exists():
        selected_df = pd.read_csv(selected_path)
        checks["selected_visual_family_count"] = int(len(selected_df))
        if "sample_count" in selected_df.columns:
            work = selected_df.copy()
            work["sample_count"] = pd.to_numeric(work["sample_count"], errors="coerce").fillna(0).astype(int)
            if "included_in_visual" in work.columns:
                included = work[
                    pd.to_numeric(work["included_in_visual"], errors="coerce").fillna(0).astype(int) == 1
                ]
            else:
                included = work
            if not included.empty:
                checks["selected_visual_family_support_floor_ok"] = bool(
                    (included["sample_count"] >= max(min_family_support, 1)).all()
                )

    trained_path = diagnostics_dir / f"trained_family_registry_{run_id}.csv"
    if trained_path.exists():
        trained_df = pd.read_csv(trained_path)
        if {"sample_count", "included_in_training"}.issubset(trained_df.columns):
            work = trained_df.copy()
            work["sample_count"] = pd.to_numeric(work["sample_count"], errors="coerce").fillna(0).astype(int)
            included = work[pd.to_numeric(work["included_in_training"], errors="coerce").fillna(0).astype(int) == 1]
            checks["trained_family_support_floor_ok"] = bool(
                not included.empty and (included["sample_count"] >= max(min_family_support, 1)).all()
            )

    confusion_path = diagnostics_dir / f"confusion_matrix_provenance_{run_id}.csv"
    if confusion_path.exists():
        conf_df = pd.read_csv(confusion_path)
        if not conf_df.empty:
            checks["confusion_eval_source_ok"] = bool(
                "eval_source" in conf_df.columns
                and conf_df["eval_source"].astype(str).str.lower().eq("test_set").all()
            )
            checks["confusion_model_ok"] = bool(
                "model_name" in conf_df.columns
                and conf_df["model_name"].astype(str).str.lower().eq("random_forest").all()
            )

    required_true = [
        "figures_nonzero_ok",
        "tables_nonzero_ok",
        "model_set_ok",
        "ablation_feature_set_ok",
        "temporal_year_scope_ok",
        "dangerous_stats_schema_ok",
        "selected_visual_family_support_floor_ok",
        "trained_family_support_floor_ok",
        "confusion_eval_source_ok",
        "confusion_model_ok",
    ]
    if strict_profile:
        failures = [key for key in required_true if not bool(checks.get(key, False))]
        if checks.get("figures_png_count", 0) != 5:
            failures.append("figures_png_count")
        if checks.get("tables_csv_count", 0) != 5:
            failures.append("tables_csv_count")
        if checks.get("jsd_pair_rows", 0) != (int(top_families) * (int(top_families) - 1)) // 2:
            failures.append("jsd_pair_rows")
        if checks.get("jsd_family_count", 0) != int(top_families):
            failures.append("jsd_family_count")
        if checks.get("selected_visual_family_count", 0) != int(top_families):
            failures.append("selected_visual_family_count")
        if failures:
            raise ValueError(
                "[PAPER2] Strict export content validation failed: "
                + ", ".join(sorted(set(failures)))
            )
    return checks


def _build_paper_ablation_table(*, source_path: Path, output_path: Path) -> None:
    """Build compact ablation table restricted to locked feature sets/models."""
    src_df = pd.read_csv(source_path)
    if src_df.empty:
        pd.DataFrame(columns=["feature_set", "model", "macro_f1", "accuracy", "delta_vs_vendoronly"]).to_csv(
            output_path,
            index=False,
        )
        return
    feature_col = (
        "Feature Set"
        if "Feature Set" in src_df.columns
        else ("feature_set" if "feature_set" in src_df.columns else ("experiment" if "experiment" in src_df.columns else ""))
    )
    model_col = "Model" if "Model" in src_df.columns else ("model" if "model" in src_df.columns else "")
    macro_col = (
        "MacroF1"
        if "MacroF1" in src_df.columns
        else ("macro_f1" if "macro_f1" in src_df.columns else ("macro_f1_score" if "macro_f1_score" in src_df.columns else ""))
    )
    acc_col = "accuracy" if "accuracy" in src_df.columns else ("Acc" if "Acc" in src_df.columns else "")
    delta_col = (
        "Delta vs VendorOnly"
        if "Delta vs VendorOnly" in src_df.columns
        else ("delta_vs_vendoronly" if "delta_vs_vendoronly" in src_df.columns else ("leakage_sensitivity_delta" if "leakage_sensitivity_delta" in src_df.columns else ""))
    )
    if not feature_col or not model_col or not macro_col:
        src_df.to_csv(output_path, index=False)
        return
    keep_features = {"permissions_only", "vendor_only", "vendor_permissions_fused"}
    model_map = {
        "rf": "random_forest",
        "random_forest": "random_forest",
        "xgb": "xgboost",
        "xgboost": "xgboost",
        "log_reg": "logistic_regression",
        "logistic_regression": "logistic_regression",
    }
    work = src_df[[feature_col, model_col, macro_col]].copy()
    work["feature_set"] = work[feature_col].astype(str).str.strip().str.lower()
    work["model"] = work[model_col].astype(str).str.strip().str.lower().map(model_map)
    work["accuracy"] = pd.to_numeric(src_df[acc_col], errors="coerce") if acc_col else np.nan
    work["delta_vs_vendoronly"] = pd.to_numeric(src_df[delta_col], errors="coerce") if delta_col else np.nan
    work = work[
        work["feature_set"].isin(keep_features)
        & work["model"].isin({"random_forest", "xgboost", "logistic_regression"})
    ].copy()
    work["macro_f1"] = pd.to_numeric(work[macro_col], errors="coerce")
    feature_order = {"permissions_only": 0, "vendor_only": 1, "vendor_permissions_fused": 2}
    model_order = {"random_forest": 0, "xgboost": 1, "logistic_regression": 2}
    work["f_order"] = work["feature_set"].map(feature_order).fillna(99).astype(int)
    work["m_order"] = work["model"].map(model_order).fillna(99).astype(int)
    out = work.sort_values(by=["f_order", "m_order"], ascending=[True, True], kind="mergesort")[
        ["feature_set", "model", "macro_f1", "accuracy", "delta_vs_vendoronly"]
    ]
    out.to_csv(output_path, index=False, float_format="%.6f")


def _build_paper_cohort_summary_table(*, samples_df: pd.DataFrame | None, run_id: str) -> pd.DataFrame:
    """Build paper cohort summary table."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return pd.DataFrame(
            [
                {
                    "run_id": str(run_id),
                    "type_slug": "",
                    "family_count": 0,
                    "sample_count": 0,
                    "pct_of_dataset": 0.0,
                    "total_samples": 0,
                    "unique_families": 0,
                    "unique_types": 0,
                    "top_family_share": 0.0,
                    "banker_share": 0.0,
                }
            ]
        )
    work = samples_df.copy()
    work["type_slug"] = work.get("type_slug", "").fillna("").astype(str).str.strip().str.lower()
    work["family_canonical"] = work.get("family_canonical", "").fillna("").astype(str).str.strip()
    total = max(int(len(work)), 1)
    grouped = (
        work.groupby("type_slug", as_index=False)
        .agg(
            family_count=("family_canonical", lambda s: int(s[s.astype(str).str.strip() != ""].nunique())),
            sample_count=("type_slug", "size"),
        )
        .sort_values(by=["sample_count", "type_slug"], ascending=[False, True], kind="mergesort")
    )
    grouped["pct_of_dataset"] = (grouped["sample_count"] / total).round(6)
    total_samples = int(len(work))
    unique_families = int(work.loc[work["family_canonical"] != "", "family_canonical"].nunique())
    unique_types = int(work.loc[work["type_slug"] != "", "type_slug"].nunique())
    family_counts = (
        work.loc[work["family_canonical"] != "", "family_canonical"]
        .value_counts(dropna=True)
        .astype(int)
    )
    top_family_share = round(float(family_counts.max()) / float(total), 6) if not family_counts.empty else 0.0
    banker_share = round(float((work["type_slug"] == "banker").sum()) / float(total), 6)
    grouped["total_samples"] = total_samples
    grouped["unique_families"] = unique_families
    grouped["unique_types"] = unique_types
    grouped["top_family_share"] = top_family_share
    grouped["banker_share"] = banker_share
    grouped.insert(0, "run_id", str(run_id))
    return grouped.reset_index(drop=True)


def _build_family_temporal_scope_table(*, samples_df: pd.DataFrame | None, run_id: str) -> pd.DataFrame:
    """Build family/type temporal scope table with first/last seen years."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return pd.DataFrame(
            columns=[
                "run_id",
                "family_canonical",
                "type_slug",
                "first_seen",
                "last_seen",
                "sample_count",
            ]
        )
    work = samples_df.copy()
    work["family_canonical"] = work.get("family_canonical", "").fillna("").astype(str).str.strip()
    work["type_slug"] = work.get("type_slug", "").fillna("").astype(str).str.strip().str.lower()
    work = work[work["family_canonical"] != ""].copy()
    if work.empty:
        return pd.DataFrame(
            columns=[
                "run_id",
                "family_canonical",
                "type_slug",
                "first_seen",
                "last_seen",
                "sample_count",
            ]
        )
    effective = pd.to_datetime(
        work["effective_first_seen_at_utc"]
        if "effective_first_seen_at_utc" in work.columns
        else pd.Series(pd.NaT, index=work.index),
        errors="coerce",
        utc=True,
    )
    itw = pd.to_datetime(
        work["vt_first_seen_itw_date"]
        if "vt_first_seen_itw_date" in work.columns
        else pd.Series(pd.NaT, index=work.index),
        errors="coerce",
        utc=True,
    )
    sub = pd.to_datetime(
        work["vt_first_submission_at_utc"]
        if "vt_first_submission_at_utc" in work.columns
        else pd.Series(pd.NaT, index=work.index),
        errors="coerce",
        utc=True,
    )
    work["time_anchor"] = effective.where(effective.notna(), itw.where(itw.notna(), sub))
    grouped = (
        work.groupby(["family_canonical", "type_slug"], as_index=False)
        .agg(
            first_seen=("time_anchor", "min"),
            last_seen=("time_anchor", "max"),
            sample_count=("family_canonical", "size"),
        )
        .sort_values(by=["sample_count", "family_canonical"], ascending=[False, True], kind="mergesort")
    )
    grouped["first_seen"] = pd.to_datetime(grouped["first_seen"], errors="coerce", utc=True).dt.date.astype(str)
    grouped["last_seen"] = pd.to_datetime(grouped["last_seen"], errors="coerce", utc=True).dt.date.astype(str)
    grouped.insert(0, "run_id", str(run_id))
    return grouped.reset_index(drop=True)


def _render_pipeline_architecture_figure(*, output_path: Path) -> None:
    """Render compact pipeline architecture figure for paper exports."""
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib import rcParams
    except Exception:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"")
        return
    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]

    steps = [
        "Cohort Selection",
        "Permission Extraction",
        "Feature Engineering",
        "Model Training (RF/XGB/LR)",
        "Evaluation + Exports",
    ]
    fig, ax = plt.subplots(figsize=(7.16, 2.4))
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0.01, 0.12), 0.43, 0.76, transform=ax.transAxes, color="#e6f2ff", zorder=0, ec="none"))
    ax.add_patch(plt.Rectangle((0.44, 0.12), 0.24, 0.76, transform=ax.transAxes, color="#fff2e6", zorder=0, ec="none"))
    ax.add_patch(plt.Rectangle((0.68, 0.12), 0.31, 0.76, transform=ax.transAxes, color="#e8f7eb", zorder=0, ec="none"))
    x_positions = [0.05, 0.25, 0.45, 0.67, 0.87]
    for idx, (xpos, label) in enumerate(zip(x_positions, steps)):
        ax.text(
            xpos,
            0.55,
            label,
            ha="center",
            va="center",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "#f6f8fb", "edgecolor": "#2f4f4f"},
            transform=ax.transAxes,
        )
        if idx < len(x_positions) - 1:
            ax.annotate(
                "",
                xy=(x_positions[idx + 1] - 0.08, 0.55),
                xytext=(xpos + 0.08, 0.55),
                arrowprops={"arrowstyle": "->", "lw": 1.0, "color": "#2f4f4f"},
                xycoords=ax.transAxes,
                textcoords=ax.transAxes,
            )
    ax.text(0.22, 0.16, "Data Preparation", ha="center", va="center", fontsize=8, color="#2a4365", transform=ax.transAxes)
    ax.text(0.56, 0.16, "Structural Analysis", ha="center", va="center", fontsize=8, color="#7b341e", transform=ax.transAxes)
    ax.text(0.84, 0.16, "ML Validation", ha="center", va="center", fontsize=8, color="#22543d", transform=ax.transAxes)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def _render_paper_type_heatmap_from_table(
    *,
    type_prevalence_path: Path,
    discriminability_path: Path,
    output_path: Path,
    top_permissions: int,
) -> bool:
    """Render publication-style type permission heatmap from run-scoped tables."""
    if not type_prevalence_path.exists():
        return False
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib import rcParams
    except Exception:
        return False
    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]
    try:
        df = pd.read_csv(type_prevalence_path)
    except Exception:
        return False
    required = {"type_slug", "permission", "prevalence"}
    if df.empty or not required.issubset(df.columns):
        return False
    df = df.copy()
    df["type_slug"] = df["type_slug"].fillna("").astype(str).str.strip().str.lower()
    df["permission"] = df["permission"].fillna("").astype(str).str.strip()
    df["prevalence"] = pd.to_numeric(df["prevalence"], errors="coerce").fillna(0.0)
    df = df[(df["type_slug"] != "") & (df["permission"] != "")]
    if df.empty:
        return False

    selected_permissions: list[str] = []
    if discriminability_path.exists():
        try:
            rank_df = pd.read_csv(discriminability_path)
            if "permission" in rank_df.columns:
                selected_permissions = (
                    rank_df["permission"].fillna("").astype(str).str.strip().loc[lambda s: s != ""].head(max(top_permissions, 1)).tolist()
                )
        except Exception:
            selected_permissions = []
    if not selected_permissions:
        selected_permissions = (
            df.groupby("permission", as_index=False)["prevalence"]
            .mean()
            .sort_values(by=["prevalence", "permission"], ascending=[False, True], kind="mergesort")
            .head(max(top_permissions, 1))["permission"]
            .astype(str)
            .tolist()
        )
    plot_df = df[df["permission"].isin(set(selected_permissions))].copy()
    if plot_df.empty:
        return False
    pivot = plot_df.pivot_table(index="type_slug", columns="permission", values="prevalence", fill_value=0.0)
    type_order = ["banker", "adware", "stealer", "sms-trojan", "rat", "spyware", "ransomware"]
    ordered_rows = [name for name in type_order if name in pivot.index] + [name for name in pivot.index if name not in type_order]
    pivot = pivot.reindex(index=ordered_rows)

    fig, ax = plt.subplots(figsize=(7.16, 3.8))
    im = ax.imshow(pivot.values, aspect="auto", cmap="Reds", vmin=0, vmax=1, interpolation="nearest")
    compact_cols = [str(col).split(".")[-1] for col in pivot.columns]
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(compact_cols, rotation=75, ha="right", fontsize=8)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index.tolist(), fontsize=9)
    ax.set_xlabel("Permission", fontsize=10)
    ax.set_ylabel("Malware Type", fontsize=10)
    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.set_xticks(np.arange(-0.5, len(pivot.columns), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(pivot.index), 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=0.25, alpha=0.4)
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Prevalence", rotation=90, fontsize=9)
    cbar.ax.tick_params(labelsize=8)

    def _permission_group(token: str) -> str:
        t = str(token).lower()
        if "sms" in t:
            return "SMS"
        if "contact" in t or "account" in t:
            return "Contacts"
        if "storage" in t or "external" in t or "media" in t:
            return "Storage"
        if "phone" in t or "call" in t:
            return "Phone"
        if "accessibility" in t or "overlay" in t or "install" in t or "boot" in t:
            return "System"
        return "Other"

    group_positions: dict[str, list[int]] = {}
    for idx, col in enumerate(pivot.columns.tolist()):
        group_positions.setdefault(_permission_group(str(col).split(".")[-1]), []).append(idx)
    for group, positions in group_positions.items():
        if not positions:
            continue
        mid = (min(positions) + max(positions)) / max(len(pivot.columns) - 1, 1)
        ax.text(
            mid,
            1.08,
            group,
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            fontsize=8,
            color="#333333",
        )
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    return True


def _render_paper_dangerous_distribution_from_table(
    *,
    dangerous_distribution_path: Path,
    output_path: Path,
) -> bool:
    """Render publication-style dangerous permission distribution chart."""
    if not dangerous_distribution_path.exists():
        return False
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib import rcParams
    except Exception:
        return False
    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]
    try:
        df = pd.read_csv(dangerous_distribution_path)
    except Exception:
        return False
    required = {"type_slug", "dangerous_count_strict_mean", "sample_count"}
    if df.empty or not required.issubset(df.columns):
        return False
    work = df.copy()
    work["type_slug"] = work["type_slug"].fillna("").astype(str).str.strip().str.lower()
    work["dangerous_count_strict_mean"] = pd.to_numeric(
        work["dangerous_count_strict_mean"], errors="coerce"
    ).fillna(0.0)
    work["sample_count"] = pd.to_numeric(work["sample_count"], errors="coerce").fillna(0).astype(int)
    work = work[work["type_slug"] != ""].copy()
    if work.empty:
        return False
    type_order = ["banker", "adware", "stealer", "sms-trojan", "rat", "spyware", "ransomware"]
    work["order"] = work["type_slug"].map({k: i for i, k in enumerate(type_order)}).fillna(99).astype(int)
    work = work.sort_values(by=["order", "type_slug"], ascending=[True, True], kind="mergesort")

    labels = [f"{t}\n(n={n})" for t, n in zip(work["type_slug"], work["sample_count"])]
    strict_vals = work["dangerous_count_strict_mean"].tolist()
    unknown_vals = (
        pd.to_numeric(work.get("dangerous_count_unknown_component_mean", 0.0), errors="coerce")
        .fillna(0.0)
        .tolist()
    )
    inclusive_vals = (
        pd.to_numeric(work.get("dangerous_count_inclusive_mean", work["dangerous_count_strict_mean"]), errors="coerce")
        .fillna(0.0)
        .tolist()
    )

    fig, ax = plt.subplots(figsize=(7.16, 3.8))
    x = np.arange(len(labels))
    width = 0.7
    b_strict = ax.bar(x, strict_vals, width, color="#c53030", label="Strict Dangerous")
    b_unknown = ax.bar(
        x,
        unknown_vals,
        width,
        bottom=np.array(strict_vals),
        color="#718096",
        label="Unknown-Protection Component",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Mean Dangerous Permission Count", fontsize=10)
    ax.set_xlabel("Malware Type", fontsize=10)
    ax.grid(axis="y", linestyle="--", alpha=0.3, linewidth=0.6)
    ax.legend(
        [b_strict, b_unknown],
        ["Strict Dangerous", "Unknown-Protection Component"],
        ncol=2,
        fontsize=7,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.18),
        frameon=False,
    )
    ax.tick_params(axis="y", labelsize=8)
    for idx, val in enumerate(inclusive_vals):
        ax.text(idx, val + 0.04, f"{val:.2f}", ha="center", va="bottom", fontsize=7)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    return True


def _render_paper_jsd_heatmap_from_pairs(
    *,
    jsd_pair_path: Path,
    output_path: Path,
) -> bool:
    """Render publication-style family JSD heatmap from compact pair table."""
    if not jsd_pair_path.exists():
        return False
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib import rcParams
    except Exception:
        return False
    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]
    try:
        pairs = pd.read_csv(jsd_pair_path)
    except Exception:
        return False
    required = {"family_a", "family_b", "js_distance"}
    if pairs.empty or not required.issubset(pairs.columns):
        return False
    work = pairs.copy()
    work["family_a"] = work["family_a"].fillna("").astype(str).str.strip()
    work["family_b"] = work["family_b"].fillna("").astype(str).str.strip()
    work["js_distance"] = pd.to_numeric(work["js_distance"], errors="coerce").fillna(0.0)
    work = work[(work["family_a"] != "") & (work["family_b"] != "")]
    if work.empty:
        return False
    families = sorted(set(work["family_a"].tolist()) | set(work["family_b"].tolist()))
    idx = {name: pos for pos, name in enumerate(families)}
    matrix = np.zeros((len(families), len(families)), dtype=float)
    for _, row in work.iterrows():
        i = idx[str(row["family_a"])]
        j = idx[str(row["family_b"])]
        val = float(row["js_distance"])
        matrix[i, j] = val
        matrix[j, i] = val
    order = list(range(len(families)))
    try:
        from scipy.cluster.hierarchy import linkage, leaves_list
        from scipy.spatial.distance import squareform

        dist_vec = squareform(matrix, checks=False)
        link = linkage(dist_vec, method="average")
        order = leaves_list(link).tolist()
    except Exception:
        order = list(range(len(families)))
    ordered_families = [families[i] for i in order]
    ordered_matrix = matrix[np.ix_(order, order)]

    fig, ax = plt.subplots(figsize=(7.16, 6.0))
    im = ax.imshow(ordered_matrix, aspect="equal", cmap="coolwarm", vmin=0, vmax=1, interpolation="nearest")
    ax.set_xticks(range(len(ordered_families)))
    ax.set_xticklabels(ordered_families, rotation=70, ha="right", fontsize=8)
    ax.set_yticks(range(len(ordered_families)))
    ax.set_yticklabels(ordered_families, fontsize=8)
    ax.set_xlabel("Family", fontsize=10)
    ax.set_ylabel("Family", fontsize=10)
    ax.tick_params(axis="both", labelsize=8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("JSD", rotation=90, fontsize=9)
    cbar.ax.tick_params(labelsize=8)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    return True


def _export_paper_figure_qc(*, fig_dir: Path, output_path: Path) -> Path:
    """Export simple figure QC report (dimensions and DPI metadata)."""
    rows: list[dict[str, Any]] = []
    try:
        from PIL import Image
    except Exception:
        Image = None  # type: ignore[assignment]
    for fig_path in sorted(fig_dir.glob("*.png")):
        row = {
            "figure_name": fig_path.name,
            "width_px": "",
            "height_px": "",
            "dpi_x": "",
            "dpi_y": "",
        }
        if Image is not None:
            try:
                with Image.open(fig_path) as im:
                    row["width_px"] = int(im.width)
                    row["height_px"] = int(im.height)
                    dpi = im.info.get("dpi")
                    if isinstance(dpi, tuple) and len(dpi) >= 2:
                        row["dpi_x"] = round(float(dpi[0]), 4)
                        row["dpi_y"] = round(float(dpi[1]), 4)
            except Exception:
                pass
        rows.append(row)
    qc_df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    qc_df.to_csv(output_path, index=False)
    return output_path


def _annotate_confusion_matrix_with_metrics(
    *,
    confusion_path: Path,
    model_comparison_csv: Path,
) -> bool:
    """Annotate exported confusion matrix with compact model metrics."""
    if not confusion_path.exists() or not model_comparison_csv.exists():
        return False
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return False
    try:
        model_df = pd.read_csv(model_comparison_csv)
    except Exception:
        return False
    if model_df.empty or "Model" not in model_df.columns:
        return False
    work = model_df.copy()
    work["Model"] = work["Model"].fillna("").astype(str).str.strip().str.lower()
    row = work[work["Model"].isin({"rf", "random_forest"})].head(1)
    if row.empty:
        return False
    acc_col = "Accuracy" if "Accuracy" in row.columns else ("Acc" if "Acc" in row.columns else "")
    macro_col = "Macro F1-Score" if "Macro F1-Score" in row.columns else ("MacroF1" if "MacroF1" in row.columns else "")
    f1_col = "F1-Score" if "F1-Score" in row.columns else ("F1" if "F1" in row.columns else "")
    if not acc_col or not macro_col or not f1_col:
        return False
    acc = float(pd.to_numeric(row.iloc[0][acc_col], errors="coerce"))
    macro = float(pd.to_numeric(row.iloc[0][macro_col], errors="coerce"))
    f1 = float(pd.to_numeric(row.iloc[0][f1_col], errors="coerce"))
    if not np.isfinite(acc) or not np.isfinite(macro) or not np.isfinite(f1):
        return False
    summary = f"Accuracy={acc:.4f}  Macro-F1={macro:.4f}  Weighted-F1={f1:.4f}"

    try:
        with Image.open(confusion_path) as img:
            img = img.convert("RGB")
            banner_h = max(56, int(img.height * 0.07))
            canvas = Image.new("RGB", (img.width, img.height + banner_h), color=(255, 255, 255))
            canvas.paste(img, (0, banner_h))
            draw = ImageDraw.Draw(canvas)
            try:
                font = ImageFont.truetype("arial.ttf", size=max(16, int(banner_h * 0.36)))
            except Exception:
                font = ImageFont.load_default()
            draw.text((16, int((banner_h - 18) / 2)), summary, fill=(20, 20, 20), font=font)
            canvas.save(confusion_path, dpi=(300, 300))
    except Exception:
        return False
    return True


def _write_evidence_readiness(
    *,
    run_root: Path,
    status: str,
    failed_checks: list[str],
    manifest: dict[str, Any],
    integrity_reason: str,
) -> Path:
    """Write machine-readable evidence readiness verdict."""
    pack_dir = run_root / "paper2_pack"
    pack_dir.mkdir(parents=True, exist_ok=True)
    checks = {
        "strict_profile": bool(manifest.get("evidence_mode", False)),
        "integrity_pass": not bool(integrity_reason),
        "fallback_used": bool(manifest.get("vendor_fallback_used", False)),
        "non_standard_features": bool(manifest.get("non_standard_features", False)),
        "mandatory_artifacts_present": "mandatory_artifacts_present" not in failed_checks,
        "deterministic_split_hash_present": bool((manifest.get("split") or {}).get("split_hash")),
        "dataset_hash_present": bool(manifest.get("dataset_hash")),
        "engine_list_hash_present": bool(manifest.get("engine_list_hash")),
        "engine_ranking_hash_present": bool(manifest.get("engine_ranking_hash")),
        "manifest_complete": bool(manifest.get("run_id")),
    }
    payload = {
        "status": str(status),
        "checks": checks,
        "failed_checks": sorted(set(failed_checks)),
        "integrity_reason": integrity_reason,
    }
    out_path = pack_dir / "evidence_readiness.json"
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return out_path


def _write_evidence_compliance_stub(
    *,
    run_root: Path,
    run_id: str,
    evidence_mode: bool,
    reason: str,
) -> Path:
    """Write minimal compliance stub for early-stop runs."""
    pack_dir = run_root / "paper2_pack"
    pack_dir.mkdir(parents=True, exist_ok=True)
    out_path = pack_dir / "evidence_compliance_summary.json"
    payload = {
        "run_id": str(run_id),
        "evidence_mode": bool(evidence_mode),
        "status": "not_ready",
        "reason": str(reason or ""),
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return out_path
