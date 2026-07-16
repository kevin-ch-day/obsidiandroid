"""Runtime and payload helpers for manifest stage assembly."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
import obsidiandroid.governance.run_manifest as run_manifest
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.governance.integrity import enforce_run_scoped_artifact_paths


def runtime_diagnostics_dir() -> Path:
    """Resolve diagnostics output directory for the current runtime mode.

    Prefer :attr:`RUNTIME_DIAGNOSTICS_DIR` (set by :func:`setup_runtime_context`).
    When unset, infer ``runs/<run_id>/diagnostics`` from ``RUNTIME_RUN_ROOT`` or
    ``RUNTIME_RUN_ID`` so manifest artifacts are not dropped under legacy
    ``output/diagnostics`` alone (which breaks run-scoped provenance checks).
    """
    runtime_diag = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    if runtime_diag:
        diagnostics_dir = Path(runtime_diag)
    else:
        run_root_raw = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
        if run_root_raw:
            diagnostics_dir = Path(run_root_raw) / "diagnostics"
        else:
            rid = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "").strip()
            output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
            if rid:
                diagnostics_dir = output_root / "runs" / rid / "diagnostics"
            else:
                diagnostics_dir = output_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    return diagnostics_dir


def resolve_run_root(run_id: str, output_root: Path) -> Path:
    """Resolve the run root for the manifest stage."""
    runtime_root_raw = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
    if runtime_root_raw:
        return Path(runtime_root_raw)
    return output_root / "runs" / run_id


def validate_run_scoped_artifact_paths(
    *,
    artifact_list: list[str],
    run_root: Path,
    output_root: Path,
    run_id: str | None = None,
) -> None:
    """Enforce strict artifact-path policy for run-scoped mode."""
    try:
        enforce_run_scoped_artifact_paths(
            artifact_paths=artifact_list,
            run_root=run_root,
            output_root=output_root,
            allow_latest=True,
            run_id=run_id,
        )
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc


def derive_terminal_run_status(
    manifest_context: dict[str, Any],
    *,
    result_code: int | None = None,
) -> str:
    """Derive the terminal run status for manifest/summary sinks.

    The runner can mark ``interrupted`` explicitly for ``KeyboardInterrupt``;
    manifest and run-summary writers should preserve that state rather than
    collapsing it into ``failed`` just because a failure reason is present.
    """
    configured_status = str(manifest_context.get("run_status", "") or "").strip().lower()
    if configured_status in {"complete", "partial", "failed", "interrupted"}:
        return configured_status

    failure_reason = str(
        manifest_context.get("failure_reason", "") or manifest_context.get("integrity_error", "")
    ).strip()
    error_type = str(manifest_context.get("error_type", "") or "").strip()
    if error_type == "KeyboardInterrupt" or failure_reason == "KeyboardInterrupt" or result_code == 130:
        return "interrupted"
    if failure_reason or (result_code not in (None, 0)):
        return "failed"
    if str(manifest_context.get("completed_stage", "") or "").strip().lower() not in {"", "manifest"}:
        return "partial"
    return "complete"


def derive_aggregate_pipeline_verdict(
    *,
    run_status_raw: str,
    result_code: int,
    rv_err: str = "",
    hostile_failed: bool = False,
    readiness_issues: list[Any] | None = None,
    failure_reason: str = "",
    canonical_v3: bool = False,
) -> str:
    """Return the canonical aggregate pipeline verdict."""
    readiness_issues = list(readiness_issues or [])
    reason = str(failure_reason or "").strip()
    if run_status_raw == "interrupted":
        return "INTERRUPTED"
    if run_status_raw == "failed" and reason.startswith("[INTEGRITY]"):
        return "INTEGRITY_STOP"
    if run_status_raw == "failed":
        return "FAILED"
    if run_status_raw == "partial":
        return "PARTIAL"
    if rv_err:
        return "FAILED" if canonical_v3 else "PASS_WITH_WARNINGS"
    if hostile_failed:
        return "FAILED" if canonical_v3 else "PASS_WITH_WARNINGS"
    if readiness_issues:
        return "PASS_WITH_WARNINGS"
    if int(result_code) != 0:
        return "FAILED"
    return "PASS"


def build_registry_payload(
    *,
    manifest_context: dict[str, Any],
    samples_df: pd.DataFrame | None,
    run_id: str,
    paper_mode: bool,
    evidence_mode: bool,
    dataset_hash: str,
) -> dict[str, Any]:
    """Build the experiment-registry payload emitted by the manifest stage."""
    selected_vendors = manifest_context.get("selected_vendors", [])
    vendor_constrained = bool(manifest_context.get("vendor_constrained_run_flag", False))
    split_meta = manifest_context.get("split", {}) if isinstance(manifest_context, dict) else {}
    split_hash = str(split_meta.get("split_hash", ""))
    vendor_set_hash = str(getattr(app_config, "RUNTIME_VENDOR_SET_HASH", ""))
    model_config_hash = str(manifest_context.get("model_config_hash", "") or "")
    effective_top_k = int(manifest_context.get("effective_top_k", 0) or 0)
    publication_mode_resolution = manifest_context.get("paper_mode", {})
    publication_ready_mode = bool(
        (
            publication_mode_resolution.get("resolved_value")
            if isinstance(publication_mode_resolution, dict)
            else paper_mode
        )
        or paper_mode
    )

    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "created_at_utc": manifest_context.get("timestamp_utc"),
        "paper_mode": paper_mode,
        "publication_ready_mode": publication_ready_mode,
        "flags": {
            "vendor_constrained": vendor_constrained,
            "gated_vendor_fallback_allowed": not paper_mode,
            "duplicate_sha_hard_fail": paper_mode,
            "evidence_mode": evidence_mode,
            "non_standard_features": bool(
                manifest_context.get(
                    "non_standard_features",
                    getattr(app_config, "RUNTIME_NON_STANDARD_FEATURES", False),
                )
            ),
        },
        "paper_mode_resolution": publication_mode_resolution,
        "publication_ready_mode_resolution": publication_mode_resolution,
        "hashes": {
            "split_hash": split_hash,
            "universe_hash": "",
            "vendor_set_hash": vendor_set_hash,
            "model_config_hash": model_config_hash,
        },
        "vendor_gate_summary": {
            "n_vendors_selected": int(len(selected_vendors)) if isinstance(selected_vendors, list) else 0,
            "min_required": safe_int_config_value(
                getattr(app_config, "FEATURE_MIN_SELECTED_VENDORS", 1),
                default=1,
            ),
            "constrained_reason": "below_min_required" if vendor_constrained else "",
            "vendor_gate_debug_path": str(getattr(app_config, "RUNTIME_VENDOR_GATE_DEBUG_PATH", "")),
            "fallback_used": bool(manifest_context.get("vendor_fallback_used", False)),
            "fallback_added_count": int(manifest_context.get("vendor_fallback_added_count", 0) or 0),
            "k_requested": int(manifest_context.get("k_requested", 0) or 0),
            "effective_top_k": effective_top_k,
            "included_engine_count": int(manifest_context.get("included_engine_count", 0) or 0),
        },
        "cohort_summary": {
            "n_samples_total": int(len(samples_df)) if isinstance(samples_df, pd.DataFrame) else 0,
            "n_families": int(samples_df["family_id"].nunique())
            if isinstance(samples_df, pd.DataFrame) and "family_id" in samples_df.columns
            else 0,
            "dataset_hash": dataset_hash,
            "unknown_excluded_count": int(manifest_context.get("unknown_excluded_count", 0) or 0),
        },
    }


def build_manifest_payload(
    *,
    manifest_context: dict[str, Any],
    profile: dict[str, Any],
    samples_df: pd.DataFrame | None,
    run_id: str,
    paper_mode: bool,
    evidence_mode: bool,
    dataset_hash: str,
    engine_names: list[str],
    parser_list: list[str],
    included_engines: int,
    excluded_engines: int,
) -> dict[str, Any]:
    """Build the core run-manifest payload before artifact attachment."""
    split_meta = manifest_context.get("split", {}) if isinstance(manifest_context, dict) else {}
    duplicate_meta = manifest_context.get("duplicate_sha", {}) if isinstance(manifest_context, dict) else {}
    selected_vendors = manifest_context.get("selected_vendors", [])
    vendor_constrained = bool(manifest_context.get("vendor_constrained_run_flag", False))
    model_config_snapshot_path = str(manifest_context.get("model_config_snapshot_path", "") or "")
    model_config_hash = str(manifest_context.get("model_config_hash", "") or "")
    vendor_set_hash = str(getattr(app_config, "RUNTIME_VENDOR_SET_HASH", ""))
    vendor_gate_debug_path = str(getattr(app_config, "RUNTIME_VENDOR_GATE_DEBUG_PATH", ""))
    non_standard_features = bool(
        manifest_context.get(
            "non_standard_features",
            getattr(app_config, "RUNTIME_NON_STANDARD_FEATURES", False),
        )
    )
    effective_top_k = int(manifest_context.get("effective_top_k", 0) or 0)
    cohort_contract = manifest_context.get("paper_cohort_contract", {})
    publication_mode_resolution = manifest_context.get("paper_mode", {})
    publication_ready_mode = bool(
        (
            publication_mode_resolution.get("resolved_value")
            if isinstance(publication_mode_resolution, dict)
            else paper_mode
        )
        or paper_mode
    )

    return {
        "run_id": run_id,
        "run_instance_id": str(manifest_context.get("run_instance_id", "") or run_id),
        "run_slot": str(manifest_context.get("run_slot", "") or ""),
        "run_root": str(manifest_context.get("run_root", "") or ""),
        "run_started_at_utc": manifest_context.get("run_started_at_utc") or manifest_context.get("timestamp_utc"),
        "run_mode": str(manifest_context.get("run_mode", "") or ""),
        "claim_surface": str(manifest_context.get("claim_surface", "") or ""),
        "profile_id": str(profile.get("profile_id", "unknown")),
        "timestamp_utc": manifest_context.get("timestamp_utc"),
        "git_commit": run_manifest.get_git_commit(),
        "config_hash": manifest_context.get("config_hash"),
        "profile_params": profile,
        "engine_list_hash": hash_payload(engine_names),
        "parser_list_hash": hash_payload(parser_list),
        "taxonomy_version": run_manifest.compute_taxonomy_version_hash(),
        "cohort_size": int(len(samples_df)) if isinstance(samples_df, pd.DataFrame) else 0,
        "cohort_sql_scope_row_count": manifest_context.get("cohort_sql_scope_row_count"),
        "cohort_prepared_row_count": manifest_context.get("cohort_prepared_row_count"),
        "gate_total_candidates": manifest_context.get("gate_total_candidates"),
        "feature_matrix_cols_post_prune": manifest_context.get("feature_matrix_cols_post_prune"),
        "analysis_snapshot": manifest_context.get("analysis_snapshot", {}),
        "selected_vendor_count": manifest_context.get("selected_vendor_count"),
        "selected_vendors": selected_vendors,
        "vendor_constrained_run_flag": vendor_constrained,
        "split": split_meta,
        "duplicate_sha": duplicate_meta,
        "vendor_gate_debug_path": vendor_gate_debug_path,
        "vendor_set_hash": vendor_set_hash,
        "model_config_snapshot_path": model_config_snapshot_path,
        "model_config_hash": model_config_hash,
        "dependency_versions": manifest_context.get("dependency_versions", {}),
        "paper_mode": publication_mode_resolution,
        "publication_ready_mode": publication_ready_mode,
        "publication_ready_mode_resolution": publication_mode_resolution,
        "evidence_mode": evidence_mode,
        "non_standard_features": non_standard_features,
        "included_engine_count": included_engines,
        "excluded_engine_count": excluded_engines,
        "engine_count_observed": int(manifest_context.get("engine_count_observed", 0) or 0),
        "engine_count_canonical": int(manifest_context.get("engine_count_canonical", 0) or 0),
        "engine_count_included_after_gating": included_engines,
        "engine_count_near_miss": int(manifest_context.get("engine_near_miss_count", 0) or 0),
        "engine_exclusion_reason_counts": dict(manifest_context.get("engine_exclusion_reason_counts", {}) or {}),
        "av_binary_feature_engine_scope": str(manifest_context.get("av_binary_feature_engine_scope", "all_observed") or "all_observed"),
        "av_binary_feature_engine_columns": int(manifest_context.get("av_binary_feature_engine_columns", 0) or 0),
        "av_binary_feature_engine_columns_observed": int(manifest_context.get("av_binary_feature_engine_columns_observed", 0) or 0),
        "engine_count_requested_top_k": int(manifest_context.get("k_requested", 0) or 0),
        "k_requested": int(manifest_context.get("k_requested", 0) or 0),
        "effective_top_k": effective_top_k,
        "vendor_fallback_used": bool(manifest_context.get("vendor_fallback_used", False)),
        "vendor_fallback_added_count": int(manifest_context.get("vendor_fallback_added_count", 0) or 0),
        "dataset_hash": dataset_hash,
        "paper_cohort_contract": cohort_contract,
        "cohort_contract": cohort_contract,
        "artifact_list": [],
        "manifest_schema_version": run_manifest.MANIFEST_SCHEMA_VERSION,
        "db_query_contract": manifest_context.get("db_query_contract", {}),
        "trained_models": [],
        "training_provenance": dict(
            getattr(app_config, "RUNTIME_TRAINING_PROVENANCE_SUMMARY", {})
            or {}
        ),
    }
