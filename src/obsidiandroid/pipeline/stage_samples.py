"""Sample loading and analysis snapshot preparation stage for the pipeline.

Canonical implementation (**Pass 68**): ``obsidiandroid.pipeline.stage_samples``;
The supported import path is ``obsidiandroid.pipeline.stage_samples``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.database import db_sample_metadata_queries
import obsidiandroid.governance.cohort_readiness_report as cohort_readiness_report
import obsidiandroid.governance.cohort_reproducibility as cohort_reproducibility
from obsidiandroid.governance.cohort_lock_manifest import build_lock_manifest_payload
from obsidiandroid.governance.label_snapshot_contract import (
    label_snapshot_hash,
    normalize_label_snapshot_frame,
)
from obsidiandroid.governance.locked_paper_materialization import materialize_locked_paper_cohort
from obsidiandroid.governance.support_floor_policy import (
    resolve_configured_min_samples_per_family,
    resolve_diagnostic_min_samples_per_family,
    resolve_membership_min_samples_per_family,
    resolve_support_floor_mode,
)
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import output_hygiene as output_hygiene_mod
from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.observability.logging import get_logger, log_event
from obsidiandroid.common.sample_metadata_preprocessor import prepare_sample_dataframe

from obsidiandroid.orchestration.profile_filters import (
    apply_dataset_filters,
)
from obsidiandroid.pipeline.contract_filters import apply_contract_filters
from obsidiandroid.diagnostics import android_authority_drift_report
from obsidiandroid.diagnostics import cohort_family_feed_risk
from obsidiandroid.diagnostics import family_label_confidence_audit
from obsidiandroid.diagnostics import cohort_foundation_export
from obsidiandroid.diagnostics import family_label_taxonomy_audit
from obsidiandroid.diagnostics import taxonomy_target_surface_report
from obsidiandroid.diagnostics import v3_label_contract
from obsidiandroid.diagnostics import cohort_vocabulary
from obsidiandroid.pipeline.sample_exports import (
    augment_dataset_time_contract as _augment_dataset_time_contract,
    diagnostics_dir as _diagnostics_dir,
    export_cohort_filter_contract as _export_cohort_filter_contract,
    export_dataset_time_contract as _export_dataset_time_contract,
    export_paper_cohort_sample_ids as _export_paper_cohort_sample_ids,
    export_time_window_family_distributions as _export_time_window_family_distributions,
    resolve_dataset_time_contract as _resolve_dataset_time_contract,
)


PIPELINE_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.pipeline.samples",
    "pipeline",
)


def _locked_snapshot_membership_is_authoritative(
    profile: dict[str, Any],
    *,
    enable_snapshot_lock: bool,
    snapshot_lock_file: str,
) -> bool:
    """Return whether a paper-locked sample-id snapshot should own cohort membership.

    Locked publication profiles preserve a historical governed cohort by exact ``sample_id``.
    Applying membership-shrinking gates before that lock can erase valid locked rows, so the
    lock must be materialized first whenever an enforceable lock is enabled and configured.
    """
    if not bool(enable_snapshot_lock):
        return False
    if not bool(profile.get("paper_locked", False)):
        return False
    return bool(str(snapshot_lock_file or "").strip())


def _can_reuse_gate_stats_from_loaded_frame(
    *,
    gates: dict[str, Any],
    lock_membership_authoritative: bool,
    limit: int | None,
    family_cap: int | None,
    type_cap: int | None,
    type_cap_by_slug: dict[str, int] | None,
    exclude_unknown_type_slug: bool,
    exclude_weak_label_kinds: bool,
    exclude_family_label_conflicts: bool,
) -> bool:
    """Return whether SQL gate stats can be derived from the loaded governed frame.

    This compatibility shortcut is safe only for the historical empty-gates path,
    where the loaded frame itself defines the governed cohort snapshot.  Any
    explicit cohort gate can affect pre/post exclusion counters, so those profiles
    must use ``get_type_cohort_gate_stats`` instead of fabricating zero-drop
    diagnostics from the already-filtered rows.
    """
    def _gate_value_is_inactive(value: Any) -> bool:
        return value is None or value is False or value in ([], {}, "")

    significant_gate_keys = {
        key
        for key, value in gates.items()
        if key not in {"require_mapped_family", "require_sha256", "allow_missing_package_name"}
        and not _gate_value_is_inactive(value)
    }
    if significant_gate_keys:
        return False
    if gates.get("require_mapped_family") is False or gates.get("require_sha256") is False:
        return False
    if gates.get("allow_missing_package_name") is False:
        return False
    if exclude_unknown_type_slug or exclude_weak_label_kinds or exclude_family_label_conflicts:
        return False
    if lock_membership_authoritative:
        return False
    if isinstance(limit, int) and limit > 0:
        return False
    if isinstance(family_cap, int) and family_cap > 0:
        return False
    if isinstance(type_cap, int) and type_cap > 0:
        return False
    if isinstance(type_cap_by_slug, dict) and any(
        str(key).strip() and isinstance(value, int) and value > 0
        for key, value in type_cap_by_slug.items()
    ):
        return False
    return True


def _build_reused_gate_stats_snapshot(
    *,
    samples_df: pd.DataFrame,
    type_slug: str | None,
    time_start_utc: str | None,
    time_end_utc: str | None,
    sql_min_support: int | None,
    sql_exclude_families: tuple[str, ...],
) -> dict[str, Any]:
    """Build a gate-stats payload from the fetched governed cohort when reuse is safe."""
    row_count = int(len(samples_df))
    return {
        "type_slug": type_slug or "all",
        "time_window_start_utc": time_start_utc,
        "time_window_end_utc": time_end_utc,
        "total_candidates": row_count,
        "excluded_unmapped_family": 0,
        "excluded_missing_sha256": 0,
        "excluded_missing_hash_registry": 0,
        "excluded_missing_package_name": 0,
        "excluded_low_support": 0,
        "excluded_unknown_type_slug": 0,
        "excluded_weak_label_kind": 0,
        "excluded_family_label_conflict": 0,
        "excluded_family_ids": [],
        "excluded_family_canonical": list(sql_exclude_families),
        "governed_cohort_count": row_count,
        "final_count_estimate": row_count,
        "final_count_estimate_sequential_legacy": row_count,
        "min_samples_per_family_applied_in_sql": sql_min_support is not None,
        "gate_stats_mode": "derived_from_loaded_governed_frame",
    }


def export_cohort_filter_summary(
    summary: dict[str, Any],
    run_id: str,
    profile_id: str,
    output_path: Path,
) -> str:
    """Write cohort filter summary CSV with run-scoped naming and global ``.latest`` mirror."""
    row = dict(summary)
    row["run_id"] = run_id
    row["profile_id"] = profile_id
    csv_text = pd.DataFrame([row]).to_csv(index=False)
    out_path = Path(output_path)
    paths = output_hygiene_mod.mirror_csv_text_run_then_global(
        diagnostics_dir=out_path.parent,
        run_filename=out_path.name,
        csv_text=csv_text,
        global_latest_name="analysis_snapshot_filter_summary.latest.csv",
    )
    return str(paths[0])


def load_and_prepare_samples(
    profile: dict[str, Any],
    profile_id: str,
    type_slug: str | None,
    run_id: str | None = None,
    artifact_list: list[str] | None = None,
    manifest_context: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Load samples and apply profile-driven quality gates.

    Args:
        profile: Active run profile configuration.
        profile_id: Resolved profile identifier used in user-facing logs.
        type_slug: Optional malware type filter.

    Returns:
        Prepared dataframe ready for downstream AV processing. The dataframe may carry
        ``attrs`` used for audits, including:

        * ``cohort_gate_stats`` — snapshot dict from ``get_type_cohort_gate_stats`` (SQL scope
          counts; field ``total_candidates`` is the SQL profile scope head count).
        * ``cohort_gate_rows`` — optional per-gate drop bookkeeping from Python filters.

    Raises:
        ValueError: If resulting cohort fails integrity checks.
    """
    gates = profile.get("cohort_gates", {}) if isinstance(profile, dict) else {}
    cohort_label = f"Android Malware Samples ({profile_id})"

    support_floor_mode = resolve_support_floor_mode(gates)
    configured_min_support = resolve_configured_min_samples_per_family(gates)
    diagnostic_min_support = resolve_diagnostic_min_samples_per_family(gates)
    min_support_guard_mode = str(gates.get("min_support_guard_mode", "") or "").strip().lower()
    if (
        bool(getattr(app_config, "PAPER_MODE_ENABLED", False))
        and min_support_guard_mode == "temporal_evidence_floor_20"
    ):
        if configured_min_support is None or configured_min_support < 20:
            raise ValueError(
                "[PROFILE] Evidence/publication-ready temporal malicious profiles require "
                "cohort_gates.min_samples_per_family >= 20."
            )
    setattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", diagnostic_min_support)
    min_support = resolve_membership_min_samples_per_family(gates)
    require_mapped = bool(gates.get("require_mapped_family", True))
    require_sha256 = bool(gates.get("require_sha256", True))
    allow_missing_pkg = bool(gates.get("allow_missing_package_name", True))
    # Enforce unknown-type exclusion early for evidence/paper runs, even when
    # profiles omit the explicit gate key.
    exclude_unknown_type_slug = bool(gates.get("exclude_unknown_type_slug", False))
    require_active_type_slug = bool(gates.get("require_active_type_slug", False))
    exclude_weak_label_kinds = bool(gates.get("exclude_weak_label_kinds", False))
    exclude_family_label_conflicts = bool(gates.get("exclude_family_label_conflicts", False))
    if not exclude_unknown_type_slug:
        exclude_unknown_type_slug = bool(getattr(app_config, "RUNTIME_EVIDENCE_MODE", False)) or bool(
            getattr(app_config, "PAPER_MODE_ENABLED", False)
        )
    limit = gates.get("limit", None)
    family_cap = gates.get("family_cap", None)
    family_cap_seed = gates.get("family_cap_seed", None)
    type_cap = gates.get("type_cap", None)
    type_cap_seed = gates.get("type_cap_seed", None)
    type_cap_by_slug = gates.get("type_cap_by_slug", None)
    time_contract = _resolve_dataset_time_contract(
        gates=gates,
        run_id=str(run_id or "unknown"),
    )
    time_start_utc = time_contract.get("start_utc")
    time_end_utc = time_contract.get("end_utc")
    require_effective_first_seen = bool(time_contract.get("require_effective_first_seen", True))
    exclude_families = gates.get("exclude_families", []) or []
    exclude_families = tuple(
        str(family).strip().lower()
        for family in exclude_families
        if str(family).strip()
    )
    include_families = gates.get("include_families", []) or []
    include_families = tuple(
        str(family).strip().lower()
        for family in include_families
        if str(family).strip()
    )
    evidence_strict_snapshot_lock = bool(
        getattr(app_config, "REQUIRE_SNAPSHOT_LOCK_IN_EVIDENCE_MODE", True)
        and getattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False)
    )
    enable_snapshot_lock = bool(
        getattr(
            app_config,
            "ENABLE_SNAPSHOT_LOCK",
            getattr(app_config, "ENABLE_COHORT_LOCK", False),
        )
    ) or evidence_strict_snapshot_lock
    snapshot_lock_file = str(
        getattr(
            app_config,
            "SNAPSHOT_LOCK_FILE",
            getattr(app_config, "COHORT_LOCK_FILE", ""),
        )
    )
    lock_membership_authoritative = _locked_snapshot_membership_is_authoritative(
        profile,
        enable_snapshot_lock=enable_snapshot_lock,
        snapshot_lock_file=snapshot_lock_file,
    )
    sql_min_support = None if lock_membership_authoritative else min_support
    sql_exclude_families = tuple() if lock_membership_authoritative else exclude_families
    reuse_gate_stats_from_loaded_frame = _can_reuse_gate_stats_from_loaded_frame(
        gates=gates if isinstance(gates, dict) else {},
        lock_membership_authoritative=lock_membership_authoritative,
        limit=limit,
        family_cap=family_cap,
        type_cap=type_cap,
        type_cap_by_slug=type_cap_by_slug,
        exclude_unknown_type_slug=exclude_unknown_type_slug,
        exclude_weak_label_kinds=exclude_weak_label_kinds,
        exclude_family_label_conflicts=exclude_family_label_conflicts,
    )
    gate_stats_snapshot: dict[str, Any] = {}
    if not reuse_gate_stats_from_loaded_frame:
        gate_stats = db_sample_metadata_queries.get_type_cohort_gate_stats(
            type_slug=type_slug,
            min_samples_per_family=sql_min_support,
            require_mapped_family=require_mapped,
            require_sha256=require_sha256,
            allow_missing_package_name=allow_missing_pkg,
            exclude_unknown_type_slug=exclude_unknown_type_slug,
            require_active_type_slug=require_active_type_slug,
            exclude_weak_label_kinds=exclude_weak_label_kinds,
            exclude_family_label_conflicts=exclude_family_label_conflicts,
            effective_time_start_utc=time_start_utc,
            effective_time_end_utc=time_end_utc,
            require_effective_first_seen=require_effective_first_seen,
            include_family_canonical=include_families,
            exclude_family_canonical=sql_exclude_families,
        )
        gate_stats_snapshot = dict(gate_stats)
        cohort_readiness_report.print_cohort_sql_scope_gate_summary(gate_stats_snapshot)
    log_event(
        PIPELINE_LOGGER,
        "samples_stage_start",
        event_id="SAMPLES_001",
        run_id=str(run_id or "unknown"),
        profile_id=profile_id,
        type_slug=type_slug,
        min_samples_per_family=sql_min_support,
    )

    current_fetch_sample_ids: set[int] = set()
    if lock_membership_authoritative:
        current_fetch_sample_ids = db_sample_metadata_queries.load_sample_ids_by_type(
            type_slug=type_slug,
            min_samples_per_family=sql_min_support,
            require_mapped_family=require_mapped,
            require_sha256=require_sha256,
            allow_missing_package_name=allow_missing_pkg,
            exclude_unknown_type_slug=exclude_unknown_type_slug,
            require_active_type_slug=require_active_type_slug,
            exclude_weak_label_kinds=exclude_weak_label_kinds,
            exclude_family_label_conflicts=exclude_family_label_conflicts,
            limit=limit,
            family_cap=family_cap,
            family_cap_seed=family_cap_seed,
            type_cap=type_cap,
            type_cap_seed=type_cap_seed,
            type_cap_by_slug=type_cap_by_slug,
            effective_time_start_utc=time_start_utc,
            effective_time_end_utc=time_end_utc,
            require_effective_first_seen=require_effective_first_seen,
            include_family_canonical=include_families,
            exclude_family_canonical=sql_exclude_families,
        )
        samples_df = pd.DataFrame({"sample_id": sorted(current_fetch_sample_ids)})
    else:
        samples_df = db_sample_metadata_queries.load_samples_by_type(
            type_slug=type_slug,
            min_samples_per_family=sql_min_support,
            require_mapped_family=require_mapped,
            require_sha256=require_sha256,
            allow_missing_package_name=allow_missing_pkg,
            exclude_unknown_type_slug=exclude_unknown_type_slug,
            require_active_type_slug=require_active_type_slug,
            exclude_weak_label_kinds=exclude_weak_label_kinds,
            exclude_family_label_conflicts=exclude_family_label_conflicts,
            limit=limit,
            family_cap=family_cap,
            family_cap_seed=family_cap_seed,
            type_cap=type_cap,
            type_cap_seed=type_cap_seed,
            type_cap_by_slug=type_cap_by_slug,
            effective_time_start_utc=time_start_utc,
            effective_time_end_utc=time_end_utc,
            require_effective_first_seen=require_effective_first_seen,
            include_family_canonical=include_families,
            exclude_family_canonical=sql_exclude_families,
        )
    if reuse_gate_stats_from_loaded_frame:
        gate_stats_snapshot = _build_reused_gate_stats_snapshot(
            samples_df=samples_df,
            type_slug=type_slug,
            time_start_utc=time_start_utc,
            time_end_utc=time_end_utc,
            sql_min_support=sql_min_support,
            sql_exclude_families=sql_exclude_families,
        )
        cohort_readiness_report.print_cohort_sql_scope_gate_summary(gate_stats_snapshot)
    if exclude_unknown_type_slug:
        before_unknown = int(len(samples_df))
        type_slug_norm = (
            samples_df["type_slug"].fillna("").astype(str).str.strip().str.lower()
            if "type_slug" in samples_df.columns
            else pd.Series([""], index=samples_df.index, dtype="object")
        )
        unknown_mask = type_slug_norm.isin({"", "unknown"})
        unknown_count = int(unknown_mask.sum())
        if unknown_count > 0:
            samples_df = samples_df[~unknown_mask].copy()
            du.print_warning(
                "[COHORT] Unknown type_slug rows remained after SQL exclusion; "
                f"removed fallback rows={unknown_count}."
            )
            log_event(
                PIPELINE_LOGGER,
                "unknown_type_fallback_filter_applied",
                event_id="SAMPLES_210",
                level="WARNING",
                run_id=str(run_id or "unknown"),
                removed_rows=unknown_count,
                before_rows=before_unknown,
                after_rows=int(len(samples_df)),
            )
    try:
        semantics_scope = (
            "sql_limited_loader_slice"
            if isinstance(limit, int) and limit > 0
            else "sql_governed_android_cohort"
        )
        samples_df.attrs["catalog_semantics_sql_scope"] = (
            cohort_foundation_export.build_catalog_semantics_summary(
                samples_df,
                scope=semantics_scope,
            )
        )
    except Exception as exc:  # pylint: disable=broad-except
        log_event(
            PIPELINE_LOGGER,
            "samples_sql_catalog_semantics_unavailable",
            event_id="SAMPLES_105",
            level="WARNING",
            run_id=str(run_id or "unknown"),
            profile_id=profile_id,
            reason=type(exc).__name__,
        )
    samples_df.attrs["sql_exclude_families_applied"] = tuple(sql_exclude_families)
    samples_df.attrs["sql_include_families_applied"] = tuple(include_families)
    samples_df.attrs["requested_include_families"] = tuple(include_families)
    samples_df.attrs["requested_exclude_families"] = tuple(exclude_families)
    samples_df.attrs["exclude_families_deferred_by_snapshot_lock"] = bool(
        lock_membership_authoritative and bool(exclude_families)
    )
    samples_df.attrs["configured_min_samples_per_family"] = configured_min_support
    samples_df.attrs["diagnostic_min_samples_per_family"] = int(diagnostic_min_support)
    samples_df.attrs["support_floor_mode"] = support_floor_mode
    samples_df.attrs["min_samples_per_family_applied_in_sql"] = sql_min_support is not None
    samples_df.attrs["min_samples_per_family_sql_value"] = sql_min_support
    samples_df.attrs["exclude_weak_label_kinds_applied_in_sql"] = exclude_weak_label_kinds
    samples_df.attrs["exclude_family_label_conflicts_applied_in_sql"] = exclude_family_label_conflicts
    samples_df.attrs["family_cap_applied_in_sql"] = bool(isinstance(family_cap, int) and family_cap > 0)
    samples_df.attrs["family_cap_sql_value"] = int(family_cap) if isinstance(family_cap, int) and family_cap > 0 else None
    samples_df.attrs["family_cap_sql_seed"] = int(family_cap_seed) if isinstance(family_cap_seed, int) else None
    samples_df.attrs["type_cap_applied_in_sql"] = bool(isinstance(type_cap, int) and type_cap > 0)
    samples_df.attrs["type_cap_sql_value"] = int(type_cap) if isinstance(type_cap, int) and type_cap > 0 else None
    samples_df.attrs["type_cap_sql_seed"] = int(type_cap_seed) if isinstance(type_cap_seed, int) else None
    samples_df.attrs["type_cap_by_slug_applied_in_sql"] = bool(isinstance(type_cap_by_slug, dict) and type_cap_by_slug)
    samples_df.attrs["type_cap_by_slug_sql_value"] = {
        str(key).strip().lower(): int(value)
        for key, value in (type_cap_by_slug or {}).items()
        if str(key).strip() and isinstance(value, int) and value > 0
    } if isinstance(type_cap_by_slug, dict) else None
    if not lock_membership_authoritative:
        try:
            governed_taxonomy_audit_artifacts = family_label_taxonomy_audit.write_family_label_taxonomy_audit(
                samples_df=samples_df,
                diagnostics_dir=_diagnostics_dir(),
                profile_id=profile_id,
                training_min_support=int(diagnostic_min_support),
                run_id=str(run_id or "unknown"),
                artifact_prefix="sql_governed_",
                print_fn=None,
            )
            if isinstance(artifact_list, list):
                for key in (
                    "family_label_taxonomy_audit_csv",
                    "family_label_taxonomy_audit_md",
                    "support_threshold_preview_csv",
                    "support_threshold_preview_md",
                ):
                    path_obj = governed_taxonomy_audit_artifacts.get(key)
                    if path_obj:
                        artifact_list.append(str(path_obj))
        except Exception as exc:  # pylint: disable=broad-except
            du.print_warning(
                f"[COHORT] SQL-governed family taxonomy/support diagnostics export skipped: {type(exc).__name__}."
            )
            log_event(
                PIPELINE_LOGGER,
                "samples_sql_governed_family_taxonomy_audit_export_failed",
                event_id="SAMPLES_324",
                level="WARNING",
                run_id=str(run_id or "unknown"),
                profile_id=profile_id,
                reason=type(exc).__name__,
            )
    if lock_membership_authoritative:
        locked_result = materialize_locked_paper_cohort(
            profile=profile,
            run_id=str(run_id or "unknown"),
            current_fetch_sample_ids=current_fetch_sample_ids,
            current_fetch_count=int(gate_stats_snapshot.get("governed_cohort_count", len(current_fetch_sample_ids)) or len(current_fetch_sample_ids)),
            snapshot_lock_file=snapshot_lock_file,
            diagnostics_dir=_diagnostics_dir(),
        )
        samples_df = locked_result.samples_df
        filter_summary = {
            "mode": "paper_locked_snapshot_membership",
            "source_total": int(gate_stats_snapshot.get("governed_cohort_count", len(samples_df)) or len(samples_df)),
            "post_filter_total": int(len(samples_df)),
            "benign_candidates": 0,
            "malicious_candidates": int(len(samples_df)),
            "unresolved_candidates": 0,
            "benign_candidate_ratio": 0.0,
            "malicious_candidate_ratio": 1.0,
            "benign_ratio_target": None,
        }
        gate_rows = [
            {
                "run_id": str(run_id or "unknown"),
                "step": 1,
                "gate_name": "paper_locked_snapshot_membership",
                "count_before": int(gate_stats_snapshot.get("governed_cohort_count", len(samples_df)) or len(samples_df)),
                "count_after": int(len(samples_df)),
                "dropped": int(
                    max(
                        int(gate_stats_snapshot.get("governed_cohort_count", len(samples_df)) or len(samples_df))
                        - int(len(samples_df)),
                        0,
                    )
                ),
                "details": "sample_id lock applied before dataset/contract gates; min_samples_per_family and exclude_families deferred from sample-stage membership",
            }
        ]
        samples_df.attrs["cohort_filter_summary"] = filter_summary
        if isinstance(artifact_list, list):
            artifact_list.extend(
                [
                    locked_result.missing_locked_members_path,
                    locked_result.label_drift_csv_path,
                    locked_result.label_drift_summary_path,
                    locked_result.label_drift_report_path,
                ]
            )
    else:
        samples_df = apply_dataset_filters(samples_df, profile)
        samples_df, gate_rows = apply_contract_filters(
            samples_df=samples_df,
            gates=gates,
            run_id=str(run_id or "unknown"),
        )
        filter_summary = samples_df.attrs.get("cohort_filter_summary", {})
    samples_df.attrs["sql_exclude_families_applied"] = tuple(sql_exclude_families)
    samples_df.attrs["sql_include_families_applied"] = tuple(include_families)
    samples_df.attrs["requested_include_families"] = tuple(include_families)
    samples_df.attrs["requested_exclude_families"] = tuple(exclude_families)
    samples_df.attrs["exclude_families_deferred_by_snapshot_lock"] = bool(
        lock_membership_authoritative and bool(exclude_families)
    )
    samples_df.attrs["configured_min_samples_per_family"] = configured_min_support
    samples_df.attrs["diagnostic_min_samples_per_family"] = int(diagnostic_min_support)
    samples_df.attrs["support_floor_mode"] = support_floor_mode
    samples_df.attrs["min_samples_per_family_applied_in_sql"] = sql_min_support is not None
    samples_df.attrs["min_samples_per_family_sql_value"] = sql_min_support
    samples_df.attrs["exclude_weak_label_kinds_applied_in_sql"] = exclude_weak_label_kinds
    samples_df.attrs["exclude_family_label_conflicts_applied_in_sql"] = exclude_family_label_conflicts
    samples_df.attrs["family_cap_applied_in_sql"] = bool(isinstance(family_cap, int) and family_cap > 0)
    samples_df.attrs["family_cap_sql_value"] = int(family_cap) if isinstance(family_cap, int) and family_cap > 0 else None
    samples_df.attrs["family_cap_sql_seed"] = int(family_cap_seed) if isinstance(family_cap_seed, int) else None
    samples_df.attrs["type_cap_applied_in_sql"] = bool(isinstance(type_cap, int) and type_cap > 0)
    samples_df.attrs["type_cap_sql_value"] = int(type_cap) if isinstance(type_cap, int) and type_cap > 0 else None
    samples_df.attrs["type_cap_sql_seed"] = int(type_cap_seed) if isinstance(type_cap_seed, int) else None
    samples_df.attrs["type_cap_by_slug_applied_in_sql"] = bool(isinstance(type_cap_by_slug, dict) and type_cap_by_slug)
    samples_df.attrs["type_cap_by_slug_sql_value"] = {
        str(key).strip().lower(): int(value)
        for key, value in (type_cap_by_slug or {}).items()
        if str(key).strip() and isinstance(value, int) and value > 0
    } if isinstance(type_cap_by_slug, dict) else None
    samples_df.attrs["cohort_gate_rows"] = gate_rows
    rid = str(run_id or "unknown")
    primary = _diagnostics_dir() / f"analysis_snapshot_filter_summary_{rid}.csv"
    summary_path = export_cohort_filter_summary(
        summary=filter_summary if isinstance(filter_summary, dict) else {},
        run_id=rid,
        profile_id=profile_id,
        output_path=primary,
    )
    if isinstance(artifact_list, list):
        artifact_list.append(summary_path)
    contract_path, gate_report_path = _export_cohort_filter_contract(
        run_id=str(run_id or "unknown"),
        profile_id=profile_id,
        gates=gates,
        gate_rows=gate_rows,
    )
    if isinstance(artifact_list, list):
        artifact_list.extend([contract_path, gate_report_path])

    if samples_df.empty:
        log_event(
            PIPELINE_LOGGER,
            "samples_stage_failed",
            event_id="SAMPLES_500",
            level="ERROR",
            reason="empty_after_filters",
            run_id=str(run_id or "unknown"),
            profile_id=profile_id,
        )
        raise ValueError("No samples found in database.")

    samples_df = prepare_sample_dataframe(
        df=samples_df,
        label=cohort_label,
        enforce_index=False,
        drop_duplicate_rows=False,
    )

    export_snapshot = bool(
        getattr(
            app_config,
            "EXPORT_ANALYSIS_SNAPSHOT",
            getattr(app_config, "EXPORT_COHORT_SNAPSHOT", True),
        )
    )
    snapshot_file = str(
        getattr(
            app_config,
            "ANALYSIS_SNAPSHOT_FILE",
            getattr(app_config, "COHORT_SNAPSHOT_FILE", ""),
        )
    )
    snapshot_meta_file = str(
        getattr(
            app_config,
            "ANALYSIS_SNAPSHOT_META_FILE",
            getattr(app_config, "COHORT_SNAPSHOT_META_FILE", ""),
        )
    )
    snapshot_conflict_file = str(
        getattr(
            app_config,
            "ANALYSIS_SNAPSHOT_CONFLICT_FILE",
            _diagnostics_dir() / f"analysis_snapshot_label_conflicts_{rid}.csv",
        )
    )
    selection_rule_version = str(
        getattr(app_config, "ANALYSIS_SELECTION_RULE_VERSION", "snapshot_v1")
    )

    if enable_snapshot_lock and not lock_membership_authoritative:
        samples_df = cohort_reproducibility.apply_analysis_snapshot_lock(
            samples_df=samples_df,
            lock_file=snapshot_lock_file,
            fail_closed=evidence_strict_snapshot_lock,
        )

    if export_snapshot:
        cohort_reproducibility.export_analysis_snapshot(
            samples_df=samples_df,
            snapshot_file=snapshot_file,
            meta_file=snapshot_meta_file,
            conflict_file=snapshot_conflict_file,
            selection_rule_version=selection_rule_version,
            run_id=str(run_id or "unknown"),
        )
        if isinstance(artifact_list, list):
            artifact_list.extend([snapshot_file, snapshot_meta_file, snapshot_conflict_file])
    time_contract = _augment_dataset_time_contract(
        time_contract=time_contract,
        samples_df=samples_df,
    )
    dataset_time_contract_path = _export_dataset_time_contract(time_contract=time_contract)
    family_artifacts = _export_time_window_family_distributions(samples_df=samples_df)
    cohort_ids_path = _export_paper_cohort_sample_ids(samples_df=samples_df)
    cohort_lock_summary_path, cohort_membership_path = _export_cohort_lock_artifacts(
        samples_df=samples_df,
        run_id=str(run_id or "unknown"),
        profile_id=profile_id,
        enable_snapshot_lock=enable_snapshot_lock,
        evidence_strict_snapshot_lock=evidence_strict_snapshot_lock,
        snapshot_lock_file=snapshot_lock_file,
        snapshot_file=snapshot_file,
        snapshot_meta_file=snapshot_meta_file,
        selection_rule_version=selection_rule_version,
        dataset_time_contract_path=dataset_time_contract_path,
        cohort_ids_path=cohort_ids_path,
    )
    if isinstance(artifact_list, list):
        artifact_list.append(dataset_time_contract_path)
        artifact_list.extend(family_artifacts)
        artifact_list.append(cohort_ids_path)
        artifact_list.extend([cohort_lock_summary_path, cohort_membership_path])

    samples_df.attrs["cohort_gate_stats"] = gate_stats_snapshot
    _attach_live_cohort_counts_to_manifest_context(
        manifest_context,
        gate_stats_snapshot=gate_stats_snapshot,
        samples_df=samples_df,
    )
    du.print_success(f"Validated {len(samples_df)} malware samples.")
    cohort_readiness_report.print_cohort_readiness_report(samples_df, gates=gates)
    log_event(
        PIPELINE_LOGGER,
        "samples_stage_complete",
        event_id="SAMPLES_200",
        run_id=str(run_id or "unknown"),
        profile_id=profile_id,
        rows=int(len(samples_df)),
        columns=int(samples_df.shape[1]),
    )

    try:
        cohort_foundation_export.export_cohort_foundation_bundle(
            diagnostics_dir=_diagnostics_dir(),
            run_id=str(run_id or "unknown"),
            profile_id=profile_id,
            profile=profile if isinstance(profile, dict) else {},
            gate_stats=gate_stats_snapshot,
            samples_df=samples_df,
            time_contract=time_contract,
            type_slug=type_slug,
            min_samples_per_family_sql=sql_min_support,
            configured_min_samples_per_family=configured_min_support,
            diagnostic_min_samples_per_family=diagnostic_min_support,
            support_floor_mode=support_floor_mode,
            artifact_list=artifact_list,
        )
    except Exception as exc:  # pylint: disable=broad-except
        du.print_warning(
            f"[COHORT] Foundation diagnostics export skipped: {type(exc).__name__}."
        )
        log_event(
            PIPELINE_LOGGER,
            "samples_foundation_export_failed",
            event_id="SAMPLES_320",
            level="WARNING",
            run_id=str(run_id or "unknown"),
            profile_id=profile_id,
            reason=type(exc).__name__,
        )

    try:
        drift_artifacts = android_authority_drift_report.export_android_authority_drift_reports(
            diagnostics_dir=_diagnostics_dir(),
            run_id=str(run_id or "unknown"),
            samples_df=samples_df,
        )
        if isinstance(artifact_list, list):
            artifact_list.extend(drift_artifacts)
    except Exception as exc:  # pylint: disable=broad-except
        du.print_warning(
            f"[COHORT] Authority-drift diagnostics export skipped: {type(exc).__name__}."
        )
        log_event(
            PIPELINE_LOGGER,
            "samples_authority_drift_export_failed",
            event_id="SAMPLES_321",
            level="WARNING",
            run_id=str(run_id or "unknown"),
            profile_id=profile_id,
            reason=type(exc).__name__,
        )

    try:
        feed_risk_artifacts = cohort_family_feed_risk.export_family_feed_risk_reports(
            diagnostics_dir=_diagnostics_dir(),
            run_id=str(run_id or "unknown"),
            samples_df=samples_df,
        )
        if isinstance(artifact_list, list):
            artifact_list.extend(feed_risk_artifacts)
    except Exception as exc:  # pylint: disable=broad-except
        du.print_warning(
            f"[COHORT] Family feed-risk diagnostics export skipped: {type(exc).__name__}."
        )
        log_event(
            PIPELINE_LOGGER,
            "samples_family_feed_risk_export_failed",
            event_id="SAMPLES_322",
            level="WARNING",
            run_id=str(run_id or "unknown"),
            profile_id=profile_id,
            reason=type(exc).__name__,
        )

    try:
        taxonomy_audit_artifacts = family_label_taxonomy_audit.write_family_label_taxonomy_audit(
            samples_df=samples_df,
            diagnostics_dir=_diagnostics_dir(),
            profile_id=profile_id,
            training_min_support=int(diagnostic_min_support),
            run_id=str(run_id or "unknown"),
            print_fn=None,
        )
        if isinstance(artifact_list, list):
            for key in (
                "family_label_taxonomy_audit_csv",
                "family_label_taxonomy_audit_md",
                "support_threshold_preview_csv",
                "support_threshold_preview_md",
            ):
                path_obj = taxonomy_audit_artifacts.get(key)
                if path_obj:
                    artifact_list.append(str(path_obj))
    except Exception as exc:  # pylint: disable=broad-except
        du.print_warning(
            f"[COHORT] Family taxonomy/support diagnostics export skipped: {type(exc).__name__}."
        )
        log_event(
            PIPELINE_LOGGER,
            "samples_family_taxonomy_audit_export_failed",
            event_id="SAMPLES_323",
            level="WARNING",
            run_id=str(run_id or "unknown"),
            profile_id=profile_id,
            reason=type(exc).__name__,
        )

    try:
        taxonomy_target_artifacts = taxonomy_target_surface_report.export_taxonomy_target_surface_reports(
            diagnostics_dir=_diagnostics_dir(),
            run_id=str(run_id or "unknown"),
            samples_df=samples_df,
            min_support=int(diagnostic_min_support),
        )
        if isinstance(artifact_list, list):
            artifact_list.extend(taxonomy_target_artifacts)
    except Exception as exc:  # pylint: disable=broad-except
        du.print_warning(
            f"[COHORT] Taxonomy target-surface diagnostics export skipped: {type(exc).__name__}."
        )
        log_event(
            PIPELINE_LOGGER,
            "samples_taxonomy_target_surface_export_failed",
            event_id="SAMPLES_324",
            level="WARNING",
            run_id=str(run_id or "unknown"),
            profile_id=profile_id,
            reason=type(exc).__name__,
        )

    try:
        label_contract_artifacts = v3_label_contract.export_v3_label_contract(
            diagnostics_dir=_diagnostics_dir(),
            run_id=str(run_id or "unknown"),
            profile=profile,
            samples_df=samples_df,
            min_support=int(diagnostic_min_support),
        )
        if isinstance(artifact_list, list):
            artifact_list.extend(label_contract_artifacts)
    except Exception as contract_exc:  # pylint: disable=broad-except
        from obsidiandroid.common.run_slots import is_canonical_v3_profile

        if is_canonical_v3_profile(profile_id):
            du.print_error(
                f"[COHORT] V3 label contract export failed for canonical profile `{profile_id}`: {contract_exc}"
            )
            raise
        du.print_warning(
            f"[COHORT] V3 label contract export skipped: {type(contract_exc).__name__}."
        )
        log_event(
            PIPELINE_LOGGER,
            "samples_v3_label_contract_export_failed",
            event_id="SAMPLES_326",
            level="WARNING",
            run_id=str(run_id or "unknown"),
            profile_id=profile_id,
            reason=type(contract_exc).__name__,
        )

    try:
        confidence_artifacts = family_label_confidence_audit.export_family_label_confidence_reports(
            diagnostics_dir=_diagnostics_dir(),
            run_id=str(run_id or "unknown"),
            samples_df=samples_df,
            min_support=int(diagnostic_min_support),
        )
        if isinstance(artifact_list, list):
            artifact_list.extend(confidence_artifacts)
    except Exception as exc:  # pylint: disable=broad-except
        du.print_warning(
            f"[COHORT] Family label-confidence audit export skipped: {type(exc).__name__}."
        )
        log_event(
            PIPELINE_LOGGER,
            "samples_family_label_confidence_export_failed",
            event_id="SAMPLES_325",
            level="WARNING",
            run_id=str(run_id or "unknown"),
            profile_id=profile_id,
            reason=type(exc).__name__,
        )

    _assert_package_name_integrity(samples_df=samples_df, gates=gates)
    return samples_df


def _attach_live_cohort_counts_to_manifest_context(
    manifest_context: dict[str, Any] | None,
    *,
    gate_stats_snapshot: dict[str, Any],
    samples_df: pd.DataFrame,
) -> None:
    """Persist samples-stage cohort counts early so failed runs keep row-funnel context."""
    if not isinstance(manifest_context, dict):
        return
    sql_scope_rows = int(gate_stats_snapshot.get("total_candidates", 0) or 0)
    prepared_rows = int(len(samples_df))
    cohort_vocabulary.attach_cohort_row_counts_to_manifest_context(
        manifest_context,
        sql_scope_row_count=sql_scope_rows,
        prepared_row_count=prepared_rows,
    )


def _assert_package_name_integrity(samples_df: pd.DataFrame, gates: dict[str, Any]) -> None:
    """Validate missing package name ratio against configured gate threshold."""
    if "android_package_name" not in samples_df.columns:
        return

    missing_pkg_pct = float(
        (
            samples_df["android_package_name"].fillna("").astype(str).str.strip() == ""
        ).mean()
        * 100
    )
    strict_evidence_mode = bool(getattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False))
    hard_fail_missing_pkg = bool(getattr(app_config, "EVIDENCE_HARD_FAIL_MISSING_PACKAGE", True))
    allow_missing_pkg = bool(gates.get("allow_missing_package_name", True))
    if strict_evidence_mode and hard_fail_missing_pkg and not allow_missing_pkg:
        max_missing_pkg_pct = 0.0
    else:
        max_missing_pkg_pct = float(gates.get("max_missing_package_pct", 10.0))
    if missing_pkg_pct > max_missing_pkg_pct:
        raise ValueError(
            f"[INTEGRITY] Missing package rate {missing_pkg_pct:.2f}% exceeds "
            f"threshold {max_missing_pkg_pct:.2f}%."
        )


def _export_cohort_lock_artifacts(
    *,
    samples_df: pd.DataFrame,
    run_id: str,
    profile_id: str,
    enable_snapshot_lock: bool,
    evidence_strict_snapshot_lock: bool,
    snapshot_lock_file: str,
    snapshot_file: str,
    snapshot_meta_file: str,
    selection_rule_version: str,
    dataset_time_contract_path: str,
    cohort_ids_path: str,
) -> tuple[str, str]:
    """Export canonical cohort lock summary and membership artifacts."""
    from obsidiandroid.diagnostics.cohort_persistence import (
        DEFAULT_COHORT_MEMBERSHIP_COLUMNS,
        export_cohort_membership_snapshot,
        normalize_membership_df,
    )

    diagnostics_dir = _diagnostics_dir()
    summary_path = diagnostics_dir / "cohort_lock_summary.json"
    manifest_path = diagnostics_dir / "cohort_lock_manifest.json"

    membership_df = normalize_membership_df(samples_df, DEFAULT_COHORT_MEMBERSHIP_COLUMNS)
    membership_paths = export_cohort_membership_snapshot(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        samples_df=samples_df,
    )
    membership_path = membership_paths[0]
    member_ids = (
        pd.to_numeric(membership_df.get("sample_id"), errors="coerce")
        .dropna()
        .astype(int)
        .drop_duplicates()
        .sort_values()
        .tolist()
        if "sample_id" in membership_df.columns
        else []
    )

    family_counts = (
        samples_df["family_canonical"].fillna("unknown").astype(str).value_counts().head(10).to_dict()
        if "family_canonical" in samples_df.columns
        else {}
    )
    type_counts = (
        samples_df["type_slug"].fillna("unknown").astype(str).value_counts().to_dict()
        if "type_slug" in samples_df.columns
        else {}
    )
    snapshot_lock_meta = samples_df.attrs.get("snapshot_lock", {})
    if not isinstance(snapshot_lock_meta, dict):
        snapshot_lock_meta = {}
    locked_paper_meta = samples_df.attrs.get("paper_locked_materialization", {})
    if not isinstance(locked_paper_meta, dict):
        locked_paper_meta = {}
    locked_label_snapshot = samples_df.attrs.get("paper_locked_label_snapshot", {})
    if not isinstance(locked_label_snapshot, dict):
        locked_label_snapshot = {}
    raw_snapshot_status = str(snapshot_lock_meta.get("status", "") or "").strip() or (
        "not_requested" if not enable_snapshot_lock else "unknown"
    )
    missing_from_db_count = int(snapshot_lock_meta.get("missing_from_db_count", 0) or 0)
    snapshot_status = raw_snapshot_status
    if (
        raw_snapshot_status == "matched"
        and bool(snapshot_lock_meta.get("applied", False))
        and missing_from_db_count > 0
    ):
        snapshot_status = "count_only_incomplete_sample_lock"

    time_window_payload: dict[str, Any] = {}
    dataset_time_contract_file = Path(str(dataset_time_contract_path))
    if dataset_time_contract_file.exists():
        try:
            loaded = json.loads(dataset_time_contract_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                time_window_payload = loaded
        except Exception:
            time_window_payload = {}

    family_count = int(samples_df["family_canonical"].nunique()) if "family_canonical" in samples_df.columns else 0
    type_count = int(samples_df["type_slug"].nunique()) if "type_slug" in samples_df.columns else 0
    top_family_support = int(max(family_counts.values()) if family_counts else 0)
    top_family_share = float(top_family_support / len(samples_df)) if len(samples_df) else 0.0
    # A lock must bind the row-level family/type labels, not merely aggregate
    # counts.  The aggregate fallback is retained only for broad diagnostic
    # frames that lack the minimal label snapshot columns.
    label_snapshot_df = normalize_label_snapshot_frame(samples_df)
    label_snapshot_path: Path | None = diagnostics_dir / f"cohort_label_snapshot_{run_id}.csv"
    label_hash = ""
    if label_snapshot_df is not None:
        label_snapshot_df.to_csv(label_snapshot_path, index=False)
        label_hash = label_snapshot_hash(label_snapshot_df)
    else:
        label_snapshot_path = None

    aggregate_taxonomy_hash = hash_payload(
        {
            "family_count": family_count,
            "type_count": type_count,
            "top_family_support": top_family_support,
            "top_family_share": round(top_family_share, 12),
            "time_window": {
                "start_utc": str(time_window_payload.get("start_utc", "") or ""),
                "end_utc": str(time_window_payload.get("end_utc", "") or ""),
                "window_semantics": str(
                    time_window_payload.get("window_semantics", "start_inclusive_end_exclusive") or ""
                ),
                "timestamp_field": str(time_window_payload.get("timestamp_field", "") or ""),
                "require_effective_first_seen": bool(
                    time_window_payload.get("require_effective_first_seen", True)
                ),
                "fallback_order": list(time_window_payload.get("fallback_order", []) or []),
            },
        }
    )
    taxonomy_hash = label_hash or aggregate_taxonomy_hash
    lock_manifest = build_lock_manifest_payload(
        lock_version=str(run_id),
        profile_id=profile_id,
        contract_id=f"{profile_id}_contract",
        created_at_utc=str(run_id),
        canonical_historical_run_id=str(run_id),
        # The manifest must point at the membership file written in this run.
        # ``paper_cohort_sample_ids.csv`` remains a convenience export for
        # downstream reports; it is not necessarily present in isolated runs
        # and therefore cannot be the immutable lock's source of membership.
        member_list_path=str(membership_path),
        sample_count=int(len(samples_df)),
        family_count=family_count,
        type_count=type_count,
        cohort_hash=hash_payload(member_ids),
        taxonomy_hash=taxonomy_hash,
        label_snapshot_path=str(label_snapshot_path or ""),
        label_snapshot_hash=label_hash,
        sql_profile_version="live_stage_samples_v1",
        profile_version=str(profile_id),
        time_window={
            "start_utc": str(time_window_payload.get("start_utc", "") or ""),
            "end_utc": str(time_window_payload.get("end_utc", "") or ""),
            "window_semantics": str(
                time_window_payload.get("window_semantics", "start_inclusive_end_exclusive") or ""
            ),
            "timestamp_field": str(time_window_payload.get("timestamp_field", "") or ""),
            "require_effective_first_seen": bool(time_window_payload.get("require_effective_first_seen", True)),
            "fallback_order": list(time_window_payload.get("fallback_order", []) or []),
            "type_scope": "all_malicious" if profile_id.endswith("_locked") else "",
        },
        top_family_support=top_family_support,
        top_family_share=round(top_family_share, 12),
    )
    manifest_path.write_text(json.dumps(lock_manifest, indent=2, sort_keys=True), encoding="utf-8")

    payload = {
        "schema_version": "1.0",
        "run_id": run_id,
        "profile_id": profile_id,
        "sample_count": int(len(samples_df)),
        "unique_family_count": family_count,
        "unique_type_count": type_count,
        "top_family_counts": family_counts,
        "type_counts": type_counts,
        "snapshot_lock": {
            "requested": bool(enable_snapshot_lock),
            "required": bool(evidence_strict_snapshot_lock),
            "status": snapshot_status,
            "selection_status": raw_snapshot_status,
            "applied": bool(snapshot_lock_meta.get("applied", False)),
            "fail_closed": bool(snapshot_lock_meta.get("fail_closed", evidence_strict_snapshot_lock)),
            "lock_file": str(snapshot_lock_file),
            "matched_sample_count": int(snapshot_lock_meta.get("matched_sample_count", 0) or 0),
            "lock_sample_count": int(snapshot_lock_meta.get("lock_sample_count", 0) or 0),
            "missing_from_db_count": missing_from_db_count,
            "snapshot_file": str(snapshot_file),
            "snapshot_meta_file": str(snapshot_meta_file),
            "selection_rule_version": str(selection_rule_version),
        },
        "artifacts": {
            "cohort_lock_manifest_json": str(manifest_path),
            "cohort_membership_csv": str(membership_path),
            "dataset_time_contract_json": str(dataset_time_contract_path),
            "paper_cohort_sample_ids_csv": str(cohort_ids_path),
            "label_snapshot_csv": str(label_snapshot_path or ""),
            "missing_locked_members_csv": str(locked_paper_meta.get("missing_locked_members_csv", "") or ""),
            "locked_paper_label_drift_csv": str(locked_paper_meta.get("label_drift_csv", "") or ""),
            "locked_paper_label_drift_summary_json": str(locked_paper_meta.get("label_drift_summary_json", "") or ""),
            "locked_paper_label_drift_report_md": str(locked_paper_meta.get("label_drift_report_md", "") or ""),
        },
        "locked_paper_materialization": dict(locked_paper_meta),
        "locked_paper_label_snapshot": dict(locked_label_snapshot),
        "label_snapshot": {
            "available": bool(label_hash),
            "path": str(label_snapshot_path or ""),
            "hash": label_hash,
            "taxonomy_hash_source": "row_level_label_snapshot" if label_hash else "aggregate_fallback",
        },
    }
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(summary_path), str(membership_path)
