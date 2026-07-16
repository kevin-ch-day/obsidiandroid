"""Run manifest stage helpers.

Canonical implementation (**Pass 69**): ``obsidiandroid.pipeline.stage_manifest``;
The supported import path is ``obsidiandroid.pipeline.stage_manifest``.

This module isolates manifest assembly/writing so orchestration code can remain
focused on pipeline step ordering.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
import obsidiandroid.governance.compliance as compliance
import obsidiandroid.governance.artifacts as artifacts
import obsidiandroid.governance.run_manifest as run_manifest
from obsidiandroid.governance.paper_constants import write_paper_constants
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.pipeline.engine_lifecycle_schema import readiness_mask
from obsidiandroid.governance.evidence_mode_resolver import coalesce_manifest_publication_mode
from obsidiandroid.common.publication_readiness import (
    evaluate_publication_ready_status,
    publication_ready_payload,
)
from obsidiandroid.pipeline.manifest.runtime_support import (
    build_manifest_payload,
    build_registry_payload,
    derive_aggregate_pipeline_verdict,
    derive_terminal_run_status,
    resolve_run_root,
    runtime_diagnostics_dir as _manifest_runtime_diagnostics_dir,
    validate_run_scoped_artifact_paths as _manifest_validate_run_scoped_artifact_paths,
)
from obsidiandroid.pipeline.manifest.paper2_strict_exports import (
    build_family_temporal_scope_table as _build_family_temporal_scope_table,
    build_paper_ablation_table as _build_paper_ablation_table,
    build_paper_cohort_summary_table as _build_paper_cohort_summary_table,
    build_strict_paper2_exports as _build_strict_paper2_exports,
)
from obsidiandroid.pipeline.manifest.paper_evidence import (
    build_manuscript_table_constants,
    build_promoted_paper_model_binding,
    write_promoted_paper_model_binding,
)
from obsidiandroid.pipeline.manifest.paper_compliance_checks import build_paper_compliance_checks

from obsidiandroid.modeling.pipeline_core import ALL_SUPPORTED_MODELS
from obsidiandroid.pipeline.manifest.stage_manifest_writers import (
    finalize_output_hygiene_bundle as _finalize_output_hygiene_bundle,
    write_evaluation_contract_json as _write_evaluation_contract_json,
    write_experiment_contract_snapshot as _write_experiment_contract_snapshot,
    write_run_summary_json as _write_run_summary_json,
    write_run_summary_onepager as _write_run_summary_onepager,
    write_taxonomy_authority_recommendation_md as _write_taxonomy_authority_recommendation_md,
)

from obsidiandroid.pipeline.manifest.stage_manifest_artifacts import (
    compute_dataset_hash as _compute_dataset_hash,
    export_engine_ranking_tiers as _export_engine_ranking_tiers,
    export_parser_quality_final as _export_parser_quality_final,
    extract_parser_list as _extract_parser_list,
    summarize_engine_lifecycle as _summarize_engine_lifecycle,
    try_add_artifact as _try_add_artifact,
    write_manifest_with_pointer as _write_manifest_with_pointer,
    write_run_artifact_index as _write_run_artifact_index,
)
from obsidiandroid.pipeline.manifest.stage_manifest_evidence_pack import (
    build_cohort_limitation_summary as _build_cohort_limitation_summary,
    build_evidence_bundle as _build_evidence_bundle,
    export_confusion_matrix_provenance as _export_confusion_matrix_provenance,
    export_trained_family_registry as _export_trained_family_registry,
    render_consensus_distribution_png as _render_consensus_distribution_png,
    write_evidence_compliance_stub as _write_evidence_compliance_stub,
    write_evidence_readiness as _write_evidence_readiness,
)
from obsidiandroid.pipeline.manifest.stage_manifest_writers import (
    compute_experiment_series_id as _compute_experiment_series_id,
)



def _runtime_diagnostics_dir() -> Path:
    """Resolve diagnostics output directory for current runtime mode."""
    return _manifest_runtime_diagnostics_dir()


def _validate_run_scoped_artifact_paths(
    *,
    artifact_list: list[str],
    run_root: Path,
    output_root: Path,
    run_id: str | None = None,
) -> None:
    """Enforce strict artifact path policy for run-scoped mode."""
    _manifest_validate_run_scoped_artifact_paths(
        artifact_list=artifact_list,
        run_root=run_root,
        output_root=output_root,
        run_id=run_id,
    )


def _populate_engine_lifecycle_manifest_context(
    manifest_context: dict[str, Any],
    pipeline_results: dict | None,
) -> None:
    """Backfill engine-gating manifest counters from a direct stage result frame."""
    if not isinstance(pipeline_results, dict):
        return
    engine_lifecycle = pipeline_results.get("engine_lifecycle")
    if not isinstance(engine_lifecycle, pd.DataFrame) or engine_lifecycle.empty:
        return

    has_near_miss_flag = "near_miss_flag" in engine_lifecycle.columns
    if "engine_near_miss_count" not in manifest_context and has_near_miss_flag:
        manifest_context["engine_near_miss_count"] = int(
            engine_lifecycle["near_miss_flag"].fillna(False).astype(bool).sum()
        )
    if "engine_exclusion_reason_counts" in manifest_context:
        return
    if "exclusion_reason" not in engine_lifecycle.columns:
        return

    included_mask = readiness_mask(engine_lifecycle)
    excluded = engine_lifecycle[~included_mask]
    reasons = excluded["exclusion_reason"].dropna().astype(str).str.strip()
    reasons = reasons[reasons != ""]
    manifest_context["engine_exclusion_reason_counts"] = {
        str(reason): int(count)
        for reason, count in reasons.value_counts().sort_index().items()
    }


def _merge_lifecycle_into_manifest(manifest: dict[str, Any], manifest_context: dict[str, Any]) -> None:
    """Align ``run_manifest.json`` lifecycle keys with run-summary derivation."""
    run_status = derive_terminal_run_status(
        manifest_context,
        result_code=int(manifest_context.get("_manifest_result_code", 0) or 0),
    )
    manifest["run_status"] = run_status
    manifest["status"] = run_status

    completed_stage = str(manifest_context.get("completed_stage", "") or "").strip()
    if not completed_stage:
        completed_stage = "manifest" if run_status == "complete" else str(
            manifest_context.get("current_stage", "") or "unknown"
        ).strip()
    manifest["completed_stage"] = completed_stage

    failed_stage = str(manifest_context.get("failed_stage", "") or "").strip()
    if failed_stage:
        manifest["failed_stage"] = failed_stage
    else:
        manifest.pop("failed_stage", None)

    failure_reason = str(
        manifest_context.get("failure_reason", "") or manifest_context.get("integrity_error", "")
    ).strip()
    if failure_reason:
        manifest["failure_reason"] = failure_reason
    else:
        manifest.pop("failure_reason", None)


def _trained_models_for_manifest(
    pipeline_results: dict | None,
    manifest_context: dict[str, Any],
) -> list[str]:
    """Resolve trained classifier keys for manifest (``pipeline_results`` or ``model_summary`` fallback)."""
    known = frozenset(ALL_SUPPORTED_MODELS)
    if isinstance(pipeline_results, dict):
        from_pipeline = sorted(k for k in pipeline_results.keys() if k in known)
        if from_pipeline:
            return from_pipeline
    ms = manifest_context.get("model_summary")
    if not isinstance(ms, dict):
        return []
    rows = ms.get("model_rows")
    if not isinstance(rows, list):
        return []
    names = {str(row["model"]).strip() for row in rows if isinstance(row, dict) and row.get("model")}
    return sorted(n for n in names if n in known)


def _apply_terminal_manifest_status(
    *,
    manifest: dict[str, Any],
    manifest_context: dict[str, Any],
    profile: dict[str, Any],
    paper_mode: bool,
    compliance_report: dict[str, Any] | None,
) -> None:
    """Attach terminal publication/evidence/lifecycle fields to the canonical manifest."""
    manifest["profile_id"] = str(profile.get("profile_id", "unknown"))
    publication_ready_status, publication_ready_reasons = evaluate_publication_ready_status(
        paper_mode=paper_mode,
        manifest=manifest,
        compliance_report=compliance_report,
    )
    manifest.update(publication_ready_payload(publication_ready_status, publication_ready_reasons))
    failed_checks = manifest_context.get("_evidence_readiness_failed_checks", [])
    if isinstance(failed_checks, list):
        manifest["evidence_readiness_failed_checks"] = sorted(
            {str(item) for item in failed_checks if str(item).strip()}
        )
    else:
        manifest["evidence_readiness_failed_checks"] = []
    manifest["evidence_readiness"] = (
        "ready" if not manifest["evidence_readiness_failed_checks"] else "not_ready"
    )
    integrity_reason = str(manifest_context.get("integrity_error", "") or "").strip()
    manifest["integrity_status"] = "pass" if not integrity_reason else "fail"
    if integrity_reason:
        manifest["integrity_reason"] = integrity_reason
    else:
        manifest.pop("integrity_reason", None)
    _merge_lifecycle_into_manifest(manifest, manifest_context)

    diagnostics_dir = _runtime_diagnostics_dir()
    failure_summary_path = str(manifest_context.get("failure_summary_path", "") or "").strip()
    if not failure_summary_path:
        candidate = diagnostics_dir / "failure_summary.json"
        if candidate.is_file():
            failure_summary_path = str(candidate)
    error_type = str(manifest_context.get("error_type", "") or "").strip()
    if not error_type and manifest.get("run_status") == "interrupted":
        error_type = "KeyboardInterrupt"

    model_summary = manifest.get("model_summary") if isinstance(manifest.get("model_summary"), dict) else {}
    top_model = str(model_summary.get("top_model", "") or "").strip()
    top_macro_f1 = model_summary.get("top_macro_f1")
    top_model_primary_metric_name = model_summary.get("top_model_primary_metric_name")
    top_model_primary_metric_value = model_summary.get("top_model_primary_metric_value")
    top_model_primary_metric_tier = model_summary.get("top_model_primary_metric_tier")
    top_model_weighted_f1_tier = model_summary.get("top_model_weighted_f1_tier")
    top_model_accuracy_tier = model_summary.get("top_model_accuracy_tier")
    trained_models = list(manifest.get("trained_models") or [])
    completed_stage = str(manifest.get("completed_stage", "") or "").strip().lower()
    training_completed = bool(
        trained_models
        or top_model
        or completed_stage in {"training", "ablation", "permission_trends", "label_resolution", "manifest"}
    )
    failure_reason = str(
        manifest_context.get("failure_reason", "") or manifest_context.get("integrity_error", "") or ""
    ).strip()

    from obsidiandroid.common.run_slots import is_canonical_v3_profile

    profile_id = str(profile.get("profile_id", "") or "unknown")
    manifest["run_diagnostics_root"] = str(diagnostics_dir)
    manifest["pipeline_verdict"] = derive_aggregate_pipeline_verdict(
        run_status_raw=str(manifest.get("run_status", "") or "").strip().lower(),
        result_code=int(manifest_context.get("_manifest_result_code", 0) or 0),
        rv_err=str(manifest_context.get("research_validity_bundle_error", "") or "").strip(),
        hostile_failed=bool(manifest_context.get("hostile_audit_failed")),
        readiness_issues=list(manifest_context.get("_evidence_readiness_failed_checks") or []),
        failure_reason=failure_reason,
        canonical_v3=is_canonical_v3_profile(profile_id),
    )
    manifest["training_completed_before_terminal"] = training_completed
    manifest["top_model"] = top_model or None
    manifest["top_model_primary_metric_name"] = (
        top_model_primary_metric_name or ("macro_f1_score" if top_macro_f1 is not None else None)
    )
    manifest["top_model_primary_metric_value"] = (
        top_model_primary_metric_value if top_model_primary_metric_value is not None else top_macro_f1
    )
    manifest["top_model_primary_metric_tier"] = top_model_primary_metric_tier or None
    manifest["top_model_weighted_f1_tier"] = top_model_weighted_f1_tier or None
    manifest["top_model_accuracy_tier"] = top_model_accuracy_tier or None
    manifest["error_type"] = error_type or None
    manifest["failure_summary_path"] = failure_summary_path or None
    if str(manifest.get("run_status", "") or "").strip().lower() == "interrupted":
        interrupted_stage = str(manifest.get("failed_stage", "") or manifest.get("completed_stage", "") or "").strip()
        manifest["interrupted_stage"] = interrupted_stage or None
    else:
        manifest.pop("interrupted_stage", None)


def _run_allows_strict_paper_exports(manifest_context: dict[str, Any]) -> tuple[bool, str]:
    """Return whether strict paper exports should run for this manifest finalization.

    Strict publication exports depend on downstream training/reporting artifacts.
    When the pipeline has already failed or stopped early, attempting to build them
    only produces a secondary error that obscures the true upstream failure.
    """
    run_status = str(manifest_context.get("run_status", "") or "").strip().lower()
    if run_status == "failed":
        return False, "run_failed"
    if run_status == "partial":
        return False, "run_partial"

    failed_stage = str(manifest_context.get("failed_stage", "") or "").strip().lower()
    if failed_stage:
        return False, f"failed_stage:{failed_stage}"

    completed_stage = str(manifest_context.get("completed_stage", "") or "").strip().lower()
    if completed_stage and completed_stage not in {"manifest", "label_resolution", "full"}:
        return False, f"completed_stage:{completed_stage}"

    integrity_error = str(manifest_context.get("integrity_error", "") or "").strip()
    if integrity_error:
        return False, "integrity_error_present"

    return True, "eligible"


def _run_allows_research_validity_bundle(manifest_context: dict[str, Any]) -> tuple[bool, str]:
    """Return whether manifest-phase research/hostile audit bundles should run."""
    run_status = str(manifest_context.get("run_status", "") or "").strip().lower()
    completed_stage = str(manifest_context.get("completed_stage", "") or "").strip().lower()
    stop_after = str(manifest_context.get("stop_after", "") or "").strip().lower()

    if run_status == "failed":
        return False, "run_failed"
    if stop_after == "samples":
        return False, "stop_after_samples"
    if run_status == "partial" and completed_stage in {"", "samples", "av_pipeline", "vendor_metadata"}:
        return False, f"run_partial:{completed_stage or 'unknown'}"
    return True, "eligible"


def _run_is_intentional_partial(manifest_context: dict[str, Any]) -> bool:
    """Return whether the current run stopped early by operator request rather than integrity failure."""
    run_status = str(manifest_context.get("run_status", "") or "").strip().lower()
    if run_status != "partial":
        return False
    stop_after = str(manifest_context.get("stop_after", "") or "").strip().lower()
    if not stop_after or stop_after == "full":
        return False
    integrity_error = str(manifest_context.get("integrity_error", "") or "").strip()
    failed_stage = str(manifest_context.get("failed_stage", "") or "").strip()
    failure_reason = str(manifest_context.get("failure_reason", "") or "").strip()
    return not any((integrity_error, failed_stage, failure_reason))


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
        evidence_mode = coalesce_manifest_publication_mode(manifest_context)
        paper_mode = evidence_mode
        output_root = oh.resolve_stable_output_root_for_mirrors()
        diagnostics_dir = _runtime_diagnostics_dir()
        run_root = resolve_run_root(run_id=run_id, output_root=output_root)
        try:
            from obsidiandroid.common.run_lifecycle import touch_run_lifecycle_running

            touch_run_lifecycle_running(run_root, stage="manifest_finalization")
        except Exception:
            pass

        from obsidiandroid.common.run_slots import is_canonical_v3_profile
        from obsidiandroid.diagnostics.cohort_persistence import resolve_effective_samples_df

        profile_id = str(profile.get("profile_id", "") or "unknown")
        if isinstance(samples_df, pd.DataFrame) and not samples_df.empty:
            manifest_context["cohort_persistence_source"] = "runtime_frame"
        else:
            resolved_samples_df = resolve_effective_samples_df(diagnostics_dir, run_id, samples_df)
            if resolved_samples_df is not None:
                samples_df = resolved_samples_df
                manifest_context["cohort_persistence_source"] = "diagnostics_export"
            else:
                manifest_context["cohort_persistence_source"] = "unavailable"

        if is_canonical_v3_profile(profile_id) and manifest_context.get("cohort_persistence_source") == "unavailable":
            du.print_error(
                f"[MANIFEST] Canonical profile `{profile_id}` cannot finalize without persisted cohort membership."
            )
            raise RuntimeError("canonical_v3_cohort_persistence_unavailable")

        included_engines, excluded_engines, engine_names = _summarize_engine_lifecycle(
            pipeline_results
        )
        _populate_engine_lifecycle_manifest_context(manifest_context, pipeline_results)
        parser_list = _extract_parser_list(vendor_eval_df)
        dataset_hash = _compute_dataset_hash(samples_df=samples_df)
        manifest_context["dataset_hash"] = dataset_hash
        if is_canonical_v3_profile(profile_id) and not str(dataset_hash or "").strip():
            du.print_error(
                f"[MANIFEST] Canonical profile `{profile_id}` requires a non-empty dataset_hash."
            )
            raise RuntimeError("canonical_v3_dataset_hash_missing")
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
        manifest["trained_models"] = _trained_models_for_manifest(pipeline_results, manifest_context)
        cohort_contract = manifest.get("cohort_contract", {}) if isinstance(manifest, dict) else {}
        contract_validation_status = str(
            (cohort_contract.get("validation", {}) if isinstance(cohort_contract.get("validation"), dict) else {}).get("status", "")
            or ""
        ).strip()
        if bool(cohort_contract.get("paper_locked", False)) and contract_validation_status == "match":
            paper_constants_path = write_paper_constants(
                run_id=run_id,
                profile_id=str(profile.get("profile_id", "unknown") or "unknown"),
                cohort_contract=cohort_contract,
                split_hash=split_hash,
                samples_df=samples_df,
                output_root=repo_root(),
            )
            manifest["paper_constants_path"] = str(paper_constants_path)
            manifest_context["paper_constants_path"] = str(paper_constants_path)
        _merge_lifecycle_into_manifest(manifest, manifest_context)
        _write_manifest_with_pointer(
            manifest=manifest,
            run_id=run_id,
            paper_mode=paper_mode,
            run_root=Path(str(getattr(app_config, "RUNTIME_RUN_ROOT", output_root))),
        )
        onepager_path = None
        if bool(getattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True)):
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
        predictions_path = diagnostics_dir / f"headline_test_predictions_{run_id}.csv"
        if (
            (paper_mode or evidence_mode)
            and predictions_path.exists()
            and str(((manifest.get("model_summary") or {})).get("top_model", "") or "").strip()
        ):
            promoted_binding_path = diagnostics_dir / f"promoted_paper_model_binding_{run_id}.json"
            promoted_binding = build_promoted_paper_model_binding(
                run_root=run_root,
                diagnostics_dir=diagnostics_dir,
                manifest=manifest,
                evidence_mode=evidence_mode,
                feature_column_hash=str(
                    getattr(app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "") or ""
                ),
            )
            write_promoted_paper_model_binding(output_path=promoted_binding_path, payload=promoted_binding)
            manifest["promoted_paper_model"] = {
                **promoted_binding,
                "binding_path": str(promoted_binding_path),
            }
            if str(promoted_binding_path) not in artifact_list:
                artifact_list.append(str(promoted_binding_path))
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
        artifact_index_path = None
        if bool(getattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True)):
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
        manifest["paper_cohort_summary"] = build_manuscript_table_constants(
            run_id=run_id,
            profile_id=str(profile.get("profile_id", "unknown") or "unknown"),
            samples_df=samples_df,
            cohort_contract=manifest.get("cohort_contract", {}) if isinstance(manifest.get("cohort_contract"), dict) else {},
        )
        allow_strict_paper_exports, skip_reason = _run_allows_strict_paper_exports(manifest_context)
        if paper_mode and not allow_strict_paper_exports:
            manifest["paper2_export_profile"] = {
                "enabled": False,
                "reason": skip_reason,
                "single_run_id": run_id,
            }
            manifest["paper_export_status"] = {
                "enabled": False,
                "reason": skip_reason,
            }
            du.print_warning(
                "[EXPORT] Strict publication export skipped because the run did not reach "
                f"a complete publication-ready state ({skip_reason})."
            )
        else:
            paper_exports = _build_strict_paper2_exports(
                run_root=run_root,
                diagnostics_dir=diagnostics_dir,
                run_id=run_id,
                samples_df=samples_df,
                manifest_context=manifest_context,
                manifest=manifest,
                profile=profile,
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
        taxonomy_mismatch_count = 0
        paper_facing_taxonomy_mismatch_count = 0
        if taxonomy_summary_path.exists():
            try:
                taxonomy_payload = json.loads(taxonomy_summary_path.read_text(encoding="utf-8"))
                taxonomy_type_rows_evaluated = int(taxonomy_payload.get("type_rows_evaluated", 0) or 0)
                taxonomy_mismatch_count = int(taxonomy_payload.get("taxonomy_mismatch_count", 0) or 0)
                paper_facing_taxonomy_mismatch_count = int(
                    taxonomy_payload.get(
                        "paper_facing_taxonomy_mismatch_count",
                        taxonomy_mismatch_count,
                    )
                    or 0
                )
            except Exception:
                taxonomy_type_rows_evaluated = 0
                taxonomy_mismatch_count = 0
                paper_facing_taxonomy_mismatch_count = 0
        taxonomy_mismatch_max_allowed = safe_int_config_value(
            getattr(app_config, "TAXONOMY_MISMATCH_STRICT_MAX_ALLOWED", 0),
            default=0,
        )

        compliance_checks = build_paper_compliance_checks(
            paper_mode=paper_mode,
            split_hash=split_hash,
            cohort_hash=str(
                ((manifest.get("cohort_contract") or {}).get("sample_id_lock") or {}).get("cohort_hash", "")
            ),
            split_audit_path=str(split_meta.get("split_audit_path", "")),
            duplicate_report_path=str(duplicate_meta.get("report_path", "")),
            duplicate_count=int(duplicate_meta.get("duplicate_sha_groups", 0) or 0),
            invalid_sha_count=int(duplicate_meta.get("invalid_sha_count", 0) or 0),
            vendor_gate_debug_path=vendor_gate_debug_path,
            run_paths_manifest_path=str(run_paths_manifest_path),
            experiment_registry_path=str(registry_path),
            taxonomy_summary_path=str(taxonomy_summary_path),
            taxonomy_type_rows_evaluated=taxonomy_type_rows_evaluated,
            taxonomy_mismatch_count=paper_facing_taxonomy_mismatch_count,
            taxonomy_mismatch_max_allowed=taxonomy_mismatch_max_allowed,
        )
        compliance_report = compliance.build_compliance_report(run_id=run_id, checks=compliance_checks)
        compliance_path = diagnostics_dir / f"paper_mode_compliance_report_{run_id}.json"
        compliance.write_compliance_report(compliance_path, compliance_report)
        manifest["paper_mode_compliance_report"] = str(compliance_path)
        _validate_run_scoped_artifact_paths(
            artifact_list=artifact_list,
            run_root=run_root,
            output_root=output_root,
            run_id=run_id,
        )
        manifest_context["research_validity_bundle_error"] = ""
        allow_research_bundle, research_skip_reason = _run_allows_research_validity_bundle(manifest_context)
        if not bool(getattr(app_config, "ENABLE_RESEARCH_VALIDITY_BUNDLE", True)):
            allow_research_bundle = False
            research_skip_reason = "config_disabled"
        if allow_research_bundle:
            manifest_context.pop("_research_bundle_skipped_reason", None)
            manifest_context.pop("_hostile_bundle_skipped_reason", None)
            _rv_wall = datetime.now(timezone.utc).isoformat()
            manifest_context["_research_bundle_wall_start_iso"] = _rv_wall
            _rv_t0 = time.perf_counter()
            try:
                from obsidiandroid.common.run_lifecycle import touch_run_lifecycle_running

                touch_run_lifecycle_running(run_root, stage="research_validity_bundle")
            except Exception:
                pass
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
                if is_canonical_v3_profile(profile_id):
                    du.print_error(
                        f"[AUDIT] Research validity bundle failed for canonical profile `{profile_id}`: {exc}"
                    )
                    raise
                du.print_warning(f"[AUDIT] Research validity bundle degraded: {exc}")
            finally:
                manifest_context["_research_bundle_duration_sec"] = max(0.0, time.perf_counter() - _rv_t0)
        else:
            manifest_context["_research_bundle_skipped_reason"] = research_skip_reason
            manifest_context["_hostile_bundle_skipped_reason"] = research_skip_reason
            manifest_context["_research_bundle_duration_sec"] = 0.0
            manifest_context["_hostile_bundle_duration_sec"] = 0.0
            du.print_info(
                "[AUDIT] Research validity and skeptic audit bundles skipped "
                f"({research_skip_reason})."
            )
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
        _merge_lifecycle_into_manifest(manifest, manifest_context)
        intentional_partial = _run_is_intentional_partial(manifest_context)
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
            _build_evidence_bundle(
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
            pack_dir = run_root / "evidence_bundle"
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
                result_code = 0 if intentional_partial else 1
                manifest_context["_manifest_result_code"] = int(result_code)
                _apply_terminal_manifest_status(
                    manifest=manifest,
                    manifest_context=manifest_context,
                    profile=profile,
                    paper_mode=paper_mode,
                    compliance_report=compliance_report,
                )
                _write_manifest_with_pointer(
                    manifest=manifest,
                    run_id=run_id,
                    paper_mode=paper_mode,
                    run_root=run_root,
                )
                _write_run_summary_json(
                    run_root=run_root,
                    diagnostics_dir=diagnostics_dir,
                    manifest_context=manifest_context,
                    manifest=manifest,
                    result_code=result_code,
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
                    result_code=result_code,
                    samples_df=samples_df,
                )
                return result_code
        if paper_mode and str(compliance_report.get("overall_status")) != "pass":
            du.print_error(f"[PAPER] Compliance failed. Report: {compliance_path}")
            fc = manifest_context.setdefault("_evidence_readiness_failed_checks", [])
            if isinstance(fc, list):
                fc.append("paper_mode_compliance_overall_fail")
            result_code = 0 if intentional_partial else 1
            manifest_context["_manifest_result_code"] = int(result_code)
            _apply_terminal_manifest_status(
                manifest=manifest,
                manifest_context=manifest_context,
                profile=profile,
                paper_mode=paper_mode,
                compliance_report=compliance_report,
            )
            _write_manifest_with_pointer(
                manifest=manifest,
                run_id=run_id,
                paper_mode=paper_mode,
                run_root=run_root,
            )
            _write_run_summary_json(
                run_root=run_root,
                diagnostics_dir=diagnostics_dir,
                manifest_context=manifest_context,
                manifest=manifest,
                result_code=result_code,
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
                result_code=result_code,
                samples_df=samples_df,
            )
            return result_code
        derived_terminal_status = derive_terminal_run_status(manifest_context)
        if derived_terminal_status == "interrupted":
            terminal_result_code = 130
        elif derived_terminal_status == "failed":
            terminal_result_code = 1
        else:
            terminal_result_code = 0
        manifest_context["_manifest_result_code"] = int(terminal_result_code)
        _apply_terminal_manifest_status(
            manifest=manifest,
            manifest_context=manifest_context,
            profile=profile,
            paper_mode=paper_mode,
            compliance_report=compliance_report,
        )
        _write_manifest_with_pointer(
            manifest=manifest,
            run_id=run_id,
            paper_mode=paper_mode,
            run_root=run_root,
        )
        _write_run_summary_json(
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            manifest_context=manifest_context,
            manifest=manifest,
            result_code=terminal_result_code,
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
            result_code=terminal_result_code,
            samples_df=samples_df,
        )
        return 0
    except Exception as exc:
        try:
            run_id = str(manifest_context.get("run_id", "unknown"))
            output_root = oh.resolve_stable_output_root_for_mirrors()
            runtime_root_raw = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
            run_root = Path(runtime_root_raw) if runtime_root_raw else (output_root / "runs" / run_id)
            evidence_mode = coalesce_manifest_publication_mode(manifest_context)
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
