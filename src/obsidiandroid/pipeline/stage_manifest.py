"""Run manifest stage helpers.

Canonical implementation (**Pass 69**): ``obsidiandroid.pipeline.stage_manifest``;
``analysis.pipeline.stage_manifest`` is an identity shim.

This module isolates manifest assembly/writing so orchestration code can remain
focused on pipeline step ordering.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import app_config
import obsidiandroid.governance.compliance as compliance
import obsidiandroid.governance.artifacts as artifacts
from obsidiandroid.common import output_paths
import obsidiandroid.governance.run_manifest as run_manifest
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.pipeline.manifest.hashing import (
    canonical_csv_bytes,
    dataset_hash_from_sample_ids,
    sha256_hex,
)
from obsidiandroid.pipeline.manifest.runtime_support import (
    build_manifest_payload,
    build_registry_payload,
    resolve_run_root,
    runtime_diagnostics_dir as _manifest_runtime_diagnostics_dir,
    validate_run_scoped_artifact_paths as _manifest_validate_run_scoped_artifact_paths,
)
from obsidiandroid.pipeline.manifest.writer import write_manifest_atomic
from obsidiandroid.pipeline.manifest.confusion_matrix_paths import (
    find_primary_confusion_matrix as _find_primary_confusion_matrix,
)
from obsidiandroid.pipeline.manifest.paper2_strict_exports import (
    build_family_temporal_scope_table as _build_family_temporal_scope_table,
    build_paper_ablation_table as _build_paper_ablation_table,
    build_paper_cohort_summary_table as _build_paper_cohort_summary_table,
    build_strict_paper2_exports as _build_strict_paper2_exports,
)
from obsidiandroid.pipeline.manifest.paper_compliance_checks import build_paper_compliance_checks

from obsidiandroid.pipeline.manifest.stage_manifest_writers import (
    compute_experiment_series_id as _compute_experiment_series_id,
    finalize_output_hygiene_bundle as _finalize_output_hygiene_bundle,
    load_previous_series_contract as _load_previous_series_contract,
    write_evaluation_contract_json as _write_evaluation_contract_json,
    write_experiment_contract_snapshot as _write_experiment_contract_snapshot,
    write_run_summary_json as _write_run_summary_json,
    write_run_summary_onepager as _write_run_summary_onepager,
    write_taxonomy_authority_recommendation_md as _write_taxonomy_authority_recommendation_md,
)


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
        manifest_context["_manifest_finalize_perf_start"] = time.perf_counter()
        manifest_context["_manifest_finalize_wall_start_iso"] = datetime.now(timezone.utc).isoformat()
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
        eval_contract_path = _write_evaluation_contract_json(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            manifest=manifest,
            manifest_context=manifest_context,
        )
        if eval_contract_path is not None and str(eval_contract_path) not in artifact_list:
            artifact_list.append(str(eval_contract_path))
        taxonomy_auth_path = _write_taxonomy_authority_recommendation_md(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            manifest_context=manifest_context,
        )
        if taxonomy_auth_path is not None and str(taxonomy_auth_path) not in artifact_list:
            artifact_list.append(str(taxonomy_auth_path))
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

        compliance_checks = build_paper_compliance_checks(
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
        manifest_context["research_validity_bundle_error"] = ""
        _rv_wall = datetime.now(timezone.utc).isoformat()
        manifest_context["_research_bundle_wall_start_iso"] = _rv_wall
        _rv_t0 = time.perf_counter()
        try:
            from obsidiandroid.diagnostics import research_validity

            research_validity.write_research_validity_bundle(
                run_root=run_root,
                diagnostics_dir=diagnostics_dir,
                run_id=run_id,
                manifest_context=manifest_context,
                manifest=manifest,
                samples_df=samples_df,
                artifact_list=artifact_list,
                paper_mode=paper_mode,
            )
        except Exception as exc:
            manifest_context["research_validity_bundle_error"] = str(exc)
            du.print_warning(f"[AUDIT] Research validity bundle degraded: {exc}")
        finally:
            manifest_context["_research_bundle_duration_sec"] = max(0.0, time.perf_counter() - _rv_t0)
        manifest["model_summary"] = manifest_context.get("model_summary") or {}
        manifest["main_training_row_authority"] = manifest_context.get("main_training_row_authority")
        manifest["trained_model_count"] = manifest_context.get("trained_model_count")
        _feat_post_prune = manifest_context.get("feature_matrix_cols_post_prune")
        if _feat_post_prune is None:
            _feat_post_prune = manifest_context.get("feature_matrix_row_count")
        manifest["feature_matrix_cols_post_prune"] = _feat_post_prune
        fused_rows = manifest_context.get("fused_feature_rows")
        if fused_rows is not None:
            try:
                fused_rows = int(fused_rows)
            except (TypeError, ValueError):
                fused_rows = None
        if fused_rows is not None:
            manifest["feature_matrix_rows"] = fused_rows

        # Legacy key: value is post-prune *column* count (historical misnomer "row_count").
        # Prefer `feature_matrix_cols_post_prune` and `feature_matrix_rows` in new code.
        manifest["feature_matrix_row_count"] = _feat_post_prune
        split_ctx = manifest_context.get("split") if isinstance(manifest_context.get("split"), dict) else {}
        manifest["train_sample_count"] = split_ctx.get("train_sample_count")
        manifest["test_sample_count"] = split_ctx.get("test_sample_count")
        manifest["ablation_multi_label_targets"] = bool(
            getattr(app_config, "ENABLE_ABLATION_MULTI_LABEL_TARGETS", True)
        )

        manifest["artifact_list"] = sorted(set(artifact_list))
        _write_manifest_with_pointer(
            manifest=manifest,
            run_id=run_id,
            paper_mode=paper_mode,
            run_root=run_root,
        )
        manifest_context["_evidence_readiness_failed_checks"] = []
        readiness_status = "ready"
        failed_checks: list[str] = []
        if evidence_mode:
            _build_paper2_pack(
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
            manifest_context["_evidence_readiness_failed_checks"] = list(sorted(set(failed_checks)))
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
                _finalize_output_hygiene_bundle(
                    run_root=run_root,
                    diagnostics_dir=diagnostics_dir,
                    run_id=run_id,
                    profile=profile,
                    manifest=manifest,
                    manifest_context=manifest_context,
                    artifact_list=artifact_list,
                    compliance_report=compliance_report,
                    paper_mode=paper_mode,
                    evidence_mode=evidence_mode,
                    result_code=1,
                )
                return 1
        if paper_mode and str(compliance_report.get("overall_status")) != "pass":
            du.print_error(f"[PAPER] Compliance failed. Report: {compliance_path}")
            fc = manifest_context.setdefault("_evidence_readiness_failed_checks", [])
            if isinstance(fc, list):
                fc.append("paper_mode_compliance_overall_fail")
            _write_run_summary_json(
                run_root=run_root,
                diagnostics_dir=diagnostics_dir,
                manifest_context=manifest_context,
                manifest=manifest,
                result_code=1,
            )
            _finalize_output_hygiene_bundle(
                run_root=run_root,
                diagnostics_dir=diagnostics_dir,
                run_id=run_id,
                profile=profile,
                manifest=manifest,
                manifest_context=manifest_context,
                artifact_list=artifact_list,
                compliance_report=compliance_report,
                paper_mode=paper_mode,
                evidence_mode=evidence_mode,
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
        _finalize_output_hygiene_bundle(
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            profile=profile,
            manifest=manifest,
            manifest_context=manifest_context,
            artifact_list=artifact_list,
            compliance_report=compliance_report,
            paper_mode=paper_mode,
            evidence_mode=evidence_mode,
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
            "**Start here for paper-style review:** `run_evidence_index.md` (run root).",
            "",
            "Authoritative source: all artifacts under this run root.",
            "",
            f"- run_root: `{run_root}`",
            f"- run_evidence_index: `{run_root / 'run_evidence_index.md'}`",
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

    headline_split = getattr(app_config, "RUNTIME_HEADLINE_SPLIT_METADATA", None)
    split_h = ""
    if isinstance(headline_split, dict):
        split_h = str(headline_split.get("split_hash", "") or "")
    feat_h = str(getattr(app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "") or "")
    provenance_df = pd.DataFrame(
        [
            {
                "run_id": str(run_id),
                "model_name": model_name,
                "eval_source": "test_set",
                "test_sample_count": int(test_samples),
                "trained_family_count": int(trained_family_count),
                "confusion_matrix_path": str(conf_path.resolve()),
                "split_hash": split_h,
                "feature_column_hash": feat_h,
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
