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
        from obsidiandroid.diagnostics import output_inventory

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

        split_blob = manifest.get("split", {}) if isinstance(manifest.get("split"), dict) else {}
        comp_rep: dict[str, Any] = {}
        comp_path_str = str(manifest.get("paper_mode_compliance_report", "") or "").strip()
        if comp_path_str:
            try:
                comp_rep = json.loads(Path(comp_path_str).read_text(encoding="utf-8"))
            except Exception:
                comp_rep = {}
        paper_status, _psr = output_inventory.evaluate_paper_safe_status(
            paper_mode=bool((manifest.get("paper_mode") or {}).get("resolved_value", False)),
            manifest=manifest,
            compliance_report=comp_rep if comp_rep else None,
        )

        feat_cols_resolved = manifest.get("feature_matrix_cols_post_prune")
        if feat_cols_resolved is None:
            feat_cols_resolved = manifest.get("feature_matrix_row_count")

        feat_rows_resolved = manifest.get("feature_matrix_rows")
        if feat_rows_resolved is None:
            feat_rows_resolved = manifest_context.get("fused_feature_rows")
        if feat_rows_resolved is not None:
            try:
                feat_rows_resolved = int(feat_rows_resolved)
            except (TypeError, ValueError):
                feat_rows_resolved = None

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
            "trained_model_count": manifest.get("trained_model_count")
            or len(list(manifest.get("trained_models") or [])),
            "main_training_row_authority": manifest.get("main_training_row_authority"),
            "feature_matrix_cols_post_prune": feat_cols_resolved,
            "feature_matrix_rows": feat_rows_resolved,
            # Legacy key retained for older tooling; this is a *column* count (post-prune).
            "feature_matrix_row_count": feat_cols_resolved,
            "train_sample_count": split_blob.get("train_sample_count"),
            "test_sample_count": split_blob.get("test_sample_count"),
            "ablation_multi_label_targets": manifest.get("ablation_multi_label_targets"),
            "paper_safe_status": paper_status,
            "manifest_path": str(run_root / "run_manifest.json"),
            "run_root": str(run_root),
            "paper_mode": bool((manifest.get("paper_mode") or {}).get("resolved_value", False)),
            "evidence_mode": bool(manifest.get("evidence_mode", False)),
            "result_code": int(result_code),
        }

        run_summary_path = run_root / "run_summary.json"
        run_summary_run_path = diagnostics_dir / f"run_summary_{run_id}.json"
        encoded = json.dumps(payload, indent=2, sort_keys=True)
        run_summary_path.write_text(encoded, encoding="utf-8")
        run_summary_run_path.write_text(encoded, encoding="utf-8")
        if oh.run_diagnostics_should_omit_latest_duplicate() and oh.path_is_under_output_runs(diagnostics_dir):
            oh.write_global_latest_text(filename="run_summary.latest.json", text=encoded)
        else:
            run_summary_latest_path = diagnostics_dir / "run_summary.latest.json"
            run_summary_latest_path.write_text(encoded, encoding="utf-8")
        return run_summary_path
    except Exception as exc:
        du.print_warning(f"[SUMMARY] Failed to write canonical run summary: {exc}")
        return None


def _finalize_output_hygiene_bundle(
    *,
    run_root: Path,
    diagnostics_dir: Path,
    run_id: str,
    profile: dict[str, Any],
    manifest: dict[str, Any],
    manifest_context: dict[str, Any],
    artifact_list: list[str],
    compliance_report: dict[str, Any] | None,
    paper_mode: bool,
    evidence_mode: bool,
    result_code: int = 0,
) -> None:
    """Artifact inventory, virtual layout, run evidence index, and terminal summary."""
    try:
        from obsidiandroid.diagnostics import output_inventory
        from obsidiandroid.observability.pipeline_observability.finalize import finalize_pipeline_observability
        from obsidiandroid.observability.pipeline_observability.run_health import print_unified_run_health

        layout_path = output_inventory.write_virtual_layout(run_root)
        inv_paths, summary = output_inventory.write_artifact_inventory_bundle(
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            manifest_paths=list(artifact_list),
            extra_summary={
                "profile_id": str(profile.get("profile_id", "")),
                "evidence_mode": evidence_mode,
                "paper_mode": paper_mode,
            },
        )

        mf_start = manifest_context.get("_manifest_finalize_perf_start")
        try:
            if isinstance(mf_start, (float, int)):
                manifest_context["_manifest_finalize_duration_sec"] = max(
                    0.0, float(time.perf_counter()) - float(mf_start),
                )
        except Exception:
            manifest_context["_manifest_finalize_duration_sec"] = 0.0

        obs_path = finalize_pipeline_observability(
            diagnostics_dir=diagnostics_dir,
            run_root=run_root,
            manifest_context=manifest_context,
            manifest=manifest,
            artifact_list=artifact_list,
            compliance_report=compliance_report,
            paper_mode=bool(paper_mode),
            evidence_mode=bool(evidence_mode),
            result_code=int(result_code),
            profile_id=str(profile.get("profile_id", "unknown")),
        )

        paper_safe_status, reasons = output_inventory.evaluate_paper_safe_status(
            paper_mode=paper_mode,
            manifest=manifest,
            compliance_report=compliance_report,
        )
        cohort_size = int(manifest.get("cohort_size", 0) or 0)
        trained_models = list(manifest.get("trained_models", []) or [])
        evidence_path = output_inventory.write_run_evidence_index_md(
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            profile_id=str(profile.get("profile_id", "unknown")),
            paper_mode=bool(paper_mode),
            cohort_size=cohort_size,
            manifest=manifest,
            manifest_context=manifest_context,
            trained_models=trained_models,
            paper_safe_status=paper_safe_status,
            paper_safe_reasons=reasons,
        )
        for p in inv_paths:
            if p and p not in artifact_list:
                artifact_list.append(p)
        if layout_path and str(layout_path) not in artifact_list:
            artifact_list.append(str(layout_path))
        if evidence_path and str(evidence_path) not in artifact_list:
            artifact_list.append(str(evidence_path))

        observability_json_path = (
            obs_path
            if obs_path is not None
            else diagnostics_dir / "run_observability_summary.json"
        )
        output_inventory.print_output_hygiene_terminal_summary(
            run_root=run_root,
            summary=summary,
            evidence_index_path=evidence_path,
            paper_safe_status=paper_safe_status,
        )
        print_unified_run_health(
            inventory_summary=summary,
            observability_json_path=observability_json_path,
            evidence_index_path=evidence_path,
            run_root=run_root,
        )
    except Exception as exc:
        du.print_warning(f"[OUTPUT] Hygiene bundle skipped: {exc}")


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
                "training_label_field": "family_id",
                "display_label_field": "family_canonical",
                "label_selection_policy": "family_id_first",
                "label_field_legacy": "family_canonical",
                "task_type": "multiclass_classification",
                "primary_metric": "macro_f1_mean_cv5",
            },
            "label_authority_reporting": {
                "training_label_field": str(
                    getattr(app_config, "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD", "") or ""
                ).strip(),
                "display_label_field": "family_canonical",
                "label_selection_policy": "family_id_first",
                "active_training_classes": getattr(
                    app_config,
                    "RUNTIME_TRAINING_LABEL_CLASS_COUNT",
                    None,
                ),
                "cohort_family_count": int(getattr(app_config, "RUNTIME_COHORT_FAMILY_COUNT", 0) or 0),
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


def _write_evaluation_contract_json(
    *,
    diagnostics_dir: Path,
    run_id: str,
    manifest: dict[str, Any],
    manifest_context: dict[str, Any],
) -> Path | None:
    """Stitch run-scoped pointers/hashes for headline evaluation evidence."""
    try:
        split_meta = manifest.get("split", {}) if isinstance(manifest, dict) else {}
        label_block = {}
        if isinstance(manifest_context, dict):
            maybe = manifest_context.get("label_authority")
            if isinstance(maybe, dict):
                label_block = maybe
        predictions_path = diagnostics_dir / f"headline_test_predictions_{run_id}.csv"
        errors_path = diagnostics_dir / f"headline_test_errors_{run_id}.csv"
        payload: dict[str, Any] = {
            "schema_version": "1.0",
            "run_id": str(run_id),
            "split_contract": {
                "split_hash": str(split_meta.get("split_hash", "") or ""),
                "split_audit_path": str(split_meta.get("split_audit_path", "") or ""),
                "split_key_hash": str(split_meta.get("split_key_hash", "") or ""),
                "train_sample_hash": str(split_meta.get("train_sample_hash", "") or ""),
                "test_sample_hash": str(split_meta.get("test_sample_hash", "") or ""),
            },
            "feature_contract": {
                "headline_feature_column_hash": str(
                    getattr(app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "") or ""
                ),
                "headline_feature_contract_path": str(
                    getattr(app_config, "RUNTIME_HEADLINE_FEATURE_CONTRACT_PATH", "") or ""
                ),
            },
            "label_authority": label_block,
            "headline_test_tables": {
                "predictions_csv": str(predictions_path),
                "predictions_csv_exists": bool(predictions_path.is_file()),
                "errors_csv": str(errors_path),
                "errors_csv_exists": bool(errors_path.is_file()),
            },
        }
        out_path = diagnostics_dir / f"evaluation_contract_{run_id}.json"
        latest_path = diagnostics_dir / "evaluation_contract.latest.json"
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        out_path.write_text(text, encoding="utf-8")
        latest_path.write_text(text, encoding="utf-8")
        return out_path
    except Exception as exc:
        du.print_warning(f"[SUMMARY] evaluation_contract export skipped: {exc}")
        return None


def _write_taxonomy_authority_recommendation_md(
    *,
    diagnostics_dir: Path,
    run_id: str,
    manifest_context: dict[str, Any],
) -> Path | None:
    """Markdown analysis-only note for taxonomy / type_slug paper safety (no policy enforcement)."""
    try:
        mismatch_path = ""
        if isinstance(manifest_context, dict):
            mismatch_path = str(manifest_context.get("taxonomy_mismatch_csv", "") or "").strip()
        lines = [
            "# Taxonomy authority recommendation (analysis-only)",
            "",
            f"Run ID: `{run_id}`",
            "",
            "## Policy",
            "",
            "- Taxonomy mapping logic is unchanged in this pass; this file is reporting only.",
            "- **type_slug** prevalence or type-level paper claims are **caution / not paper-safe** until a single authoritative type source is declared and reconciled.",
            "",
        ]
        if not mismatch_path or not Path(mismatch_path).is_file():
            lines.append("_No taxonomy mismatch export path recorded on this run._\n")
        else:
            df = pd.read_csv(mismatch_path)
            lines.append(f"Source: `{mismatch_path}` — {len(df)} row(s)\n")
            if not df.empty and "mismatch_reason" in df.columns:
                lines.append("## Mismatch reasons (top counts)\n")
                counts = df["mismatch_reason"].fillna("unknown").astype(str).value_counts().head(15)
                for reason, cnt in counts.items():
                    lines.append(f"- {reason}: {int(cnt)}")
                lines.append("")
            if not df.empty and {"type_slug", "type_slug_expected"} <= set(df.columns):
                lines.append("## Top mismatch pairs (observed type_slug, expected type_slug)\n")
                lines.append("| observed | expected | count |")
                lines.append("| --- | --- | --- |")
                pairs: dict[tuple[str, str], int] = {}
                for ts, te in zip(
                    df["type_slug"].fillna("").astype(str).str.strip().tolist(),
                    df["type_slug_expected"].fillna("").astype(str).str.strip().tolist(),
                ):
                    pairs[(ts, te)] = pairs.get((ts, te), 0) + 1
                sorted_pairs = sorted(pairs.items(), key=lambda kv: kv[1], reverse=True)[:25]
                for (ts, te), cnt in sorted_pairs:
                    lines.append(f"| `{ts}` | `{te}` | {int(cnt)} |")
                lines.append("")
            if not df.empty:
                lines.append("## Paper-facing recommendation\n")
                lines.append("")
                lines.append("- **Treat type_slug-derived quantitative claims as paper-safe:** no (pending governance).")
                lines.append("- **Suggested authority:** designate one authoritative type source for reporting; reconcile `type_mapping_mismatch` rows explicitly.\n")
        body = "\n".join(lines).strip() + "\n"
        out_path = diagnostics_dir / f"taxonomy_authority_recommendation_{run_id}.md"
        latest_path = diagnostics_dir / "taxonomy_authority_recommendation.latest.md"
        out_path.write_text(body, encoding="utf-8")
        latest_path.write_text(body, encoding="utf-8")
        return out_path
    except Exception as exc:
        du.print_warning(f"[SUMMARY] taxonomy_authority_recommendation skipped: {exc}")
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
