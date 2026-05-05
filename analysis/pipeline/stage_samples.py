"""Sample loading and analysis snapshot preparation stage for the pipeline."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from config import app_config
from database import db_sample_metadata_queries
import obsidiandroid.governance.cohort_readiness_report as cohort_readiness_report
import obsidiandroid.governance.cohort_reproducibility as cohort_reproducibility
from obsidiandroid.cli.ui import display as du
from obsidiandroid.observability.logging import get_logger, log_event
from obsidiandroid.common.sample_metadata_preprocessor import prepare_sample_dataframe

from analysis.orchestration.profile_filters import (
    apply_dataset_filters,
    export_cohort_filter_summary,
)
from analysis.pipeline.contract_filters import apply_contract_filters
from obsidiandroid.diagnostics import cohort_foundation_export
from analysis.pipeline.sample_exports import (
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

def load_and_prepare_samples(
    profile: dict[str, Any],
    profile_id: str,
    type_slug: str | None,
    run_id: str | None = None,
    artifact_list: list[str] | None = None,
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

    configured_min_support = int(gates.get("min_samples_per_family", 3))
    if bool(getattr(app_config, "PAPER_MODE_ENABLED", False)) and str(profile_id).startswith("paper2_"):
        if configured_min_support < 20:
            raise ValueError(
                "[PROFILE] paper2_* profiles require cohort_gates.min_samples_per_family >= 20 in paper mode."
            )
    setattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", configured_min_support)
    min_support = configured_min_support
    if not type_slug:
        if isinstance(gates, dict) and "min_samples_per_family" in gates:
            du.print_warning(
                "[COHORT] cohort_gates.min_samples_per_family is not applied in the SQL cohort loader "
                "when type_slug_filter is null (all-type cohort). Per-family minimums are enforced later "
                "during supervised training / CV. "
                f"Profile value={configured_min_support} is still stored as RUNTIME_MIN_FAMILY_SUPPORT."
            )
        min_support = None
    require_mapped = bool(gates.get("require_mapped_family", True))
    require_sha256 = bool(gates.get("require_sha256", True))
    allow_missing_pkg = bool(gates.get("allow_missing_package_name", True))
    # Enforce unknown-type exclusion early for evidence/paper runs, even when
    # profiles omit the explicit gate key.
    exclude_unknown_type_slug = bool(gates.get("exclude_unknown_type_slug", False))
    if not exclude_unknown_type_slug:
        exclude_unknown_type_slug = bool(getattr(app_config, "RUNTIME_EVIDENCE_MODE", False)) or bool(
            getattr(app_config, "PAPER_MODE_ENABLED", False)
        )
    limit = gates.get("limit", None)
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

    gate_stats = db_sample_metadata_queries.get_type_cohort_gate_stats(
        type_slug=type_slug,
        min_samples_per_family=min_support,
        require_mapped_family=require_mapped,
        require_sha256=require_sha256,
        allow_missing_package_name=allow_missing_pkg,
        exclude_unknown_type_slug=exclude_unknown_type_slug,
        effective_time_start_utc=time_start_utc,
        effective_time_end_utc=time_end_utc,
        require_effective_first_seen=require_effective_first_seen,
        exclude_family_canonical=exclude_families,
    )
    gate_stats_snapshot: dict[str, Any] = dict(gate_stats)
    cohort_readiness_report.print_cohort_sql_scope_gate_summary(gate_stats)
    log_event(
        PIPELINE_LOGGER,
        "samples_stage_start",
        run_id=str(run_id or "unknown"),
        profile_id=profile_id,
        type_slug=type_slug,
        min_samples_per_family=min_support,
    )

    samples_df = db_sample_metadata_queries.load_samples_by_type(
        type_slug=type_slug,
        min_samples_per_family=min_support,
        require_mapped_family=require_mapped,
        require_sha256=require_sha256,
        allow_missing_package_name=allow_missing_pkg,
        exclude_unknown_type_slug=exclude_unknown_type_slug,
        limit=limit,
        effective_time_start_utc=time_start_utc,
        effective_time_end_utc=time_end_utc,
        require_effective_first_seen=require_effective_first_seen,
        exclude_family_canonical=exclude_families,
    )
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
                run_id=str(run_id or "unknown"),
                removed_rows=unknown_count,
                before_rows=before_unknown,
                after_rows=int(len(samples_df)),
            )
    samples_df.attrs["sql_exclude_families_applied"] = tuple(exclude_families)
    samples_df = apply_dataset_filters(samples_df, profile)
    samples_df, gate_rows = apply_contract_filters(
        samples_df=samples_df,
        gates=gates,
        run_id=str(run_id or "unknown"),
    )
    samples_df.attrs["cohort_gate_rows"] = gate_rows
    filter_summary = samples_df.attrs.get("cohort_filter_summary", {})
    snapshot_filter_path = _diagnostics_dir() / "analysis_snapshot_filter_summary.latest.csv"
    summary_path = export_cohort_filter_summary(
        summary=filter_summary if isinstance(filter_summary, dict) else {},
        run_id=str(run_id or "unknown"),
        profile_id=profile_id,
        output_path=snapshot_filter_path,
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
            _diagnostics_dir() / "analysis_snapshot_label_conflicts.latest.csv",
        )
    )
    selection_rule_version = str(
        getattr(app_config, "ANALYSIS_SELECTION_RULE_VERSION", "snapshot_v1")
    )

    if enable_snapshot_lock:
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

    du.print_success(f"Validated {len(samples_df)} malware samples.")
    cohort_readiness_report.print_cohort_readiness_report(samples_df, gates=gates)
    log_event(
        PIPELINE_LOGGER,
        "samples_stage_complete",
        run_id=str(run_id or "unknown"),
        profile_id=profile_id,
        rows=int(len(samples_df)),
        columns=int(samples_df.shape[1]),
    )

    samples_df.attrs["cohort_gate_stats"] = gate_stats_snapshot
    cohort_foundation_export.export_cohort_foundation_bundle(
        diagnostics_dir=_diagnostics_dir(),
        run_id=str(run_id or "unknown"),
        profile_id=profile_id,
        profile=profile if isinstance(profile, dict) else {},
        gate_stats=gate_stats_snapshot,
        samples_df=samples_df,
        time_contract=time_contract,
        type_slug=type_slug,
        min_samples_per_family_sql=min_support,
        configured_min_samples_per_family=configured_min_support,
        artifact_list=artifact_list,
    )

    _assert_package_name_integrity(samples_df=samples_df, gates=gates)
    return samples_df


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
    diagnostics_dir = _diagnostics_dir()
    membership_path = diagnostics_dir / "cohort_membership.csv"
    summary_path = diagnostics_dir / "cohort_lock_summary.json"

    export_columns = [
        "sample_id",
        "sha256",
        "family_id",
        "family_canonical",
        "type_slug",
        "android_package_name",
        "effective_first_seen_at_utc",
        "vt_first_submission_at_utc",
    ]
    available_columns = [column for column in export_columns if column in samples_df.columns]
    membership_df = samples_df[available_columns].copy() if available_columns else samples_df.copy()
    if "sample_id" in membership_df.columns:
        membership_df["sample_id"] = pd.to_numeric(membership_df["sample_id"], errors="coerce")
        membership_df = membership_df.sort_values("sample_id", kind="mergesort")
    membership_df.to_csv(membership_path, index=False)

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
    snapshot_status = str(snapshot_lock_meta.get("status", "") or "").strip() or (
        "not_requested" if not enable_snapshot_lock else "unknown"
    )

    payload = {
        "schema_version": "1.0",
        "run_id": run_id,
        "profile_id": profile_id,
        "sample_count": int(len(samples_df)),
        "unique_family_count": int(samples_df["family_canonical"].nunique()) if "family_canonical" in samples_df.columns else 0,
        "unique_type_count": int(samples_df["type_slug"].nunique()) if "type_slug" in samples_df.columns else 0,
        "top_family_counts": family_counts,
        "type_counts": type_counts,
        "snapshot_lock": {
            "requested": bool(enable_snapshot_lock),
            "required": bool(evidence_strict_snapshot_lock),
            "status": snapshot_status,
            "applied": bool(snapshot_lock_meta.get("applied", False)),
            "fail_closed": bool(snapshot_lock_meta.get("fail_closed", evidence_strict_snapshot_lock)),
            "lock_file": str(snapshot_lock_file),
            "matched_sample_count": int(snapshot_lock_meta.get("matched_sample_count", 0) or 0),
            "lock_sample_count": int(snapshot_lock_meta.get("lock_sample_count", 0) or 0),
            "missing_from_db_count": int(snapshot_lock_meta.get("missing_from_db_count", 0) or 0),
            "snapshot_file": str(snapshot_file),
            "snapshot_meta_file": str(snapshot_meta_file),
            "selection_rule_version": str(selection_rule_version),
        },
        "artifacts": {
            "cohort_membership_csv": str(membership_path),
            "dataset_time_contract_json": str(dataset_time_contract_path),
            "paper_cohort_sample_ids_csv": str(cohort_ids_path),
        },
    }
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(summary_path), str(membership_path)
