"""Locked-cohort gap audit helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import json
import pandas as pd

from obsidiandroid.common.hash_utils import hash_payload


WEAK_LABEL_KINDS = {"filename", "hash_like", "opaque_string", "unclassified"}
UNKNOWN_TYPE_VALUES = {"", "unknown"}


@dataclass(frozen=True)
class CohortGatePolicy:
    """Gate settings needed for live-vs-lock gap auditing."""

    min_samples_per_family: int | None
    require_mapped_family: bool
    require_sha256: bool
    allow_missing_package_name: bool
    exclude_unknown_type_slug: bool
    exclude_weak_label_kinds: bool
    exclude_family_label_conflicts: bool
    exclude_families: tuple[str, ...]
    time_window_start_utc: str
    time_window_end_utc: str
    require_effective_first_seen: bool
    type_slug_filter: str | None = None


def policy_from_profile(profile: dict[str, Any]) -> CohortGatePolicy:
    """Extract current governed gate policy from a profile."""
    gates = profile.get("cohort_gates", {}) if isinstance(profile.get("cohort_gates"), dict) else {}
    exclude_families = tuple(
        str(value).strip().lower()
        for value in (gates.get("exclude_families", []) or [])
        if str(value).strip()
    )
    type_slug_filter = profile.get("type_slug_filter")
    return CohortGatePolicy(
        min_samples_per_family=(
            int(gates.get("min_samples_per_family"))
            if gates.get("min_samples_per_family") not in (None, "")
            else None
        ),
        require_mapped_family=bool(gates.get("require_mapped_family", True)),
        require_sha256=bool(gates.get("require_sha256", True)),
        allow_missing_package_name=bool(gates.get("allow_missing_package_name", True)),
        exclude_unknown_type_slug=bool(gates.get("exclude_unknown_type_slug", False)),
        exclude_weak_label_kinds=bool(gates.get("exclude_weak_label_kinds", False)),
        exclude_family_label_conflicts=bool(gates.get("exclude_family_label_conflicts", False)),
        exclude_families=exclude_families,
        time_window_start_utc=str(gates.get("time_window_start_utc", "") or ""),
        time_window_end_utc=str(gates.get("time_window_end_utc", "") or ""),
        require_effective_first_seen=bool(gates.get("require_effective_first_seen", True)),
        type_slug_filter=(str(type_slug_filter).strip().lower() if type_slug_filter not in (None, "") else None),
    )


def _normalize_df(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    if "sample_id" in df.columns:
        df["sample_id"] = pd.to_numeric(df["sample_id"], errors="coerce")
        df = df.dropna(subset=["sample_id"])
        df["sample_id"] = df["sample_id"].astype(int)
    for column in (
        "sha256",
        "family_canonical",
        "family_label",
        "type_slug",
        "sample_label_kind",
        "source_batch_label",
        "android_package_name",
    ):
        if column in df.columns:
            df[column] = df[column].fillna("").astype(str)
    if "effective_first_seen_at_utc" in df.columns:
        df["effective_first_seen_at_utc"] = pd.to_datetime(
            df["effective_first_seen_at_utc"], errors="coerce", utc=True
        )
    if "vt_first_submission_at_utc" in df.columns:
        df["vt_first_submission_at_utc"] = pd.to_datetime(
            df["vt_first_submission_at_utc"], errors="coerce", utc=True
        )
    return df


def _effective_ts(df: pd.DataFrame) -> pd.Series:
    eff = (
        df["effective_first_seen_at_utc"]
        if "effective_first_seen_at_utc" in df.columns
        else pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    )
    sub = (
        df["vt_first_submission_at_utc"]
        if "vt_first_submission_at_utc" in df.columns
        else pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    )
    return eff.fillna(sub)


def _mapped_family_mask(df: pd.DataFrame) -> pd.Series:
    family_name = (
        df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
        if "family_canonical" in df.columns
        else pd.Series("", index=df.index, dtype="object")
    )
    family_id_present = (
        pd.to_numeric(df["family_id"], errors="coerce").notna()
        if "family_id" in df.columns
        else pd.Series(False, index=df.index)
    )
    return family_id_present | (~family_name.isin({"", "unknown", "other", "unmapped", "none", "null"}))


def _family_label_conflict_mask(df: pd.DataFrame) -> pd.Series:
    raw = (
        df["family_label"].fillna("").astype(str).str.strip().str.lower()
        if "family_label" in df.columns
        else pd.Series("", index=df.index, dtype="object")
    )
    canonical = (
        df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
        if "family_canonical" in df.columns
        else pd.Series("", index=df.index, dtype="object")
    )
    return (
        ~raw.isin({"", "unknown", "generic", "unclassified", "unlabeled"})
        & ~canonical.isin({"", "unknown", "other", "unmapped", "none", "null"})
        & (raw != canonical)
    )


def _reason_series(df: pd.DataFrame, policy: CohortGatePolicy) -> pd.Series:
    """Assign a primary current-gate exclusion reason for each catalog row."""
    effective_ts = _effective_ts(df)
    family_norm = (
        df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
        if "family_canonical" in df.columns
        else pd.Series("", index=df.index, dtype="object")
    )
    type_norm = (
        df["type_slug"].fillna("").astype(str).str.strip().str.lower()
        if "type_slug" in df.columns
        else pd.Series("", index=df.index, dtype="object")
    )
    sample_label_kind = (
        df["sample_label_kind"].fillna("").astype(str).str.strip().str.lower()
        if "sample_label_kind" in df.columns
        else pd.Series("", index=df.index, dtype="object")
    )
    pkg_norm = (
        df["android_package_name"].fillna("").astype(str).str.strip()
        if "android_package_name" in df.columns
        else pd.Series("", index=df.index, dtype="object")
    )
    sha_norm = (
        df["sha256"].fillna("").astype(str).str.strip().str.lower()
        if "sha256" in df.columns
        else pd.Series("", index=df.index, dtype="object")
    )
    mapped_family = _mapped_family_mask(df)
    family_conflict = _family_label_conflict_mask(df)

    allowed_for_support = pd.Series(True, index=df.index)
    if policy.type_slug_filter:
        allowed_for_support &= type_norm.eq(policy.type_slug_filter)
    if policy.require_mapped_family:
        allowed_for_support &= mapped_family
    if policy.require_sha256:
        allowed_for_support &= sha_norm.str.len().eq(64)
    if not policy.allow_missing_package_name:
        allowed_for_support &= pkg_norm.ne("")
    if policy.exclude_unknown_type_slug:
        allowed_for_support &= ~type_norm.isin(UNKNOWN_TYPE_VALUES)
    if policy.exclude_weak_label_kinds:
        allowed_for_support &= ~sample_label_kind.isin(WEAK_LABEL_KINDS)
    if policy.exclude_family_label_conflicts:
        allowed_for_support &= ~family_conflict
    if policy.require_effective_first_seen:
        allowed_for_support &= effective_ts.notna()
    if policy.time_window_start_utc:
        allowed_for_support &= effective_ts.ge(pd.Timestamp(policy.time_window_start_utc))
    if policy.time_window_end_utc:
        allowed_for_support &= effective_ts.lt(pd.Timestamp(policy.time_window_end_utc))
    if policy.exclude_families:
        allowed_for_support &= ~family_norm.isin(set(policy.exclude_families))

    family_support_counts = (
        family_norm[allowed_for_support & ~family_norm.isin({"", "unknown", "other", "unmapped", "none", "null"})]
        .value_counts()
        .to_dict()
    )
    family_support = family_norm.map(lambda value: int(family_support_counts.get(value, 0)))
    below_min_support = (
        policy.min_samples_per_family is not None
        and allowed_for_support
        & (family_support < int(policy.min_samples_per_family))
    )

    reasons = pd.Series("", index=df.index, dtype="object")
    if policy.type_slug_filter:
        reasons.loc[type_norm.ne(policy.type_slug_filter)] = "outside_profile_type_scope"
    if policy.require_sha256:
        reasons.loc[reasons.eq("") & ~sha_norm.str.len().eq(64)] = "missing_sha256"
    if policy.require_mapped_family:
        reasons.loc[reasons.eq("") & ~mapped_family] = "missing_mapped_family"
    if policy.exclude_unknown_type_slug:
        reasons.loc[reasons.eq("") & type_norm.isin(UNKNOWN_TYPE_VALUES)] = "unknown_type_slug"
    if policy.exclude_weak_label_kinds:
        reasons.loc[reasons.eq("") & sample_label_kind.isin(WEAK_LABEL_KINDS)] = "weak_label_kind"
    if policy.exclude_family_label_conflicts:
        reasons.loc[reasons.eq("") & family_conflict] = "family_label_conflict"
    if not policy.allow_missing_package_name:
        reasons.loc[reasons.eq("") & pkg_norm.eq("")] = "missing_package_name"
    if policy.require_effective_first_seen:
        reasons.loc[reasons.eq("") & effective_ts.isna()] = "missing_effective_first_seen"
    if policy.time_window_start_utc:
        reasons.loc[
            reasons.eq("") & effective_ts.notna() & effective_ts.lt(pd.Timestamp(policy.time_window_start_utc))
        ] = "outside_time_window"
    if policy.time_window_end_utc:
        reasons.loc[
            reasons.eq("") & effective_ts.notna() & effective_ts.ge(pd.Timestamp(policy.time_window_end_utc))
        ] = "outside_time_window"
    if policy.exclude_families:
        reasons.loc[reasons.eq("") & family_norm.isin(set(policy.exclude_families))] = "excluded_family"
    if isinstance(below_min_support, pd.Series):
        reasons.loc[reasons.eq("") & below_min_support] = "below_min_samples_per_family"
    reasons.loc[reasons.eq("")] = "eligible_current_governed"
    return reasons


def build_cohort_gap_audit(
    *,
    lock_members_df: pd.DataFrame,
    current_governed_df: pd.DataFrame,
    full_catalog_df: pd.DataFrame,
    policy: CohortGatePolicy,
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Build cohort gap audit tables from frozen, current, and full catalog slices."""
    locked = _normalize_df(lock_members_df)
    current = _normalize_df(current_governed_df)
    catalog = _normalize_df(full_catalog_df)

    lock_ids = set(locked["sample_id"].tolist()) if "sample_id" in locked.columns else set()
    current_ids = set(current["sample_id"].tolist()) if "sample_id" in current.columns else set()
    catalog_ids = set(catalog["sample_id"].tolist()) if "sample_id" in catalog.columns else set()

    catalog = catalog.copy()
    catalog["current_gate_reason"] = _reason_series(catalog, policy)
    catalog["in_locked_membership"] = catalog["sample_id"].isin(lock_ids)
    catalog["in_current_governed"] = catalog["sample_id"].isin(current_ids)

    union_ids = sorted(lock_ids | current_ids)
    overlap = pd.DataFrame({"sample_id": union_ids})
    metadata_cols = [
        "sample_id",
        "sha256",
        "family_id",
        "family_canonical",
        "type_slug",
        "source_batch_label",
        "android_package_name",
        "effective_first_seen_at_utc",
        "vt_first_submission_at_utc",
        "current_gate_reason",
    ]
    catalog_meta = catalog[[col for col in metadata_cols if col in catalog.columns]].drop_duplicates("sample_id")
    current_meta = current[[col for col in metadata_cols if col in current.columns]].drop_duplicates("sample_id")
    overlap = overlap.merge(catalog_meta, on="sample_id", how="left", suffixes=("", "_catalog"))
    overlap = overlap.merge(
        current_meta.rename(
            columns={
                "family_canonical": "family_canonical_current",
                "type_slug": "type_slug_current",
                "source_batch_label": "source_batch_label_current",
            }
        ),
        on="sample_id",
        how="left",
    )
    overlap["in_locked_membership"] = overlap["sample_id"].isin(lock_ids)
    overlap["in_current_governed"] = overlap["sample_id"].isin(current_ids)
    overlap["in_full_catalog"] = overlap["sample_id"].isin(catalog_ids)

    locked_failures = overlap[overlap["in_locked_membership"] & ~overlap["in_current_governed"]].copy()
    locked_failures.loc[~locked_failures["in_full_catalog"], "current_gate_reason"] = "missing_from_full_catalog"

    governed_missing_from_lock = current.loc[~current["sample_id"].isin(lock_ids)].copy()
    by_family = (
        governed_missing_from_lock.assign(
            family_canonical=governed_missing_from_lock["family_canonical"].replace("", "<blank>")
        )
        .groupby("family_canonical", dropna=False)
        .agg(rows=("sample_id", "count"))
        .reset_index()
        .sort_values(["rows", "family_canonical"], ascending=[False, True], kind="mergesort")
    )
    by_source = (
        governed_missing_from_lock.assign(
            source_batch_label=governed_missing_from_lock["source_batch_label"].replace("", "<blank>")
        )
        .groupby("source_batch_label", dropna=False)
        .agg(rows=("sample_id", "count"))
        .reset_index()
        .sort_values(["rows", "source_batch_label"], ascending=[False, True], kind="mergesort")
    )
    exclusion_counts = (
        catalog.loc[~catalog["in_current_governed"]]
        .groupby("current_gate_reason", dropna=False)
        .agg(rows=("sample_id", "count"))
        .reset_index()
        .rename(columns={"current_gate_reason": "exclusion_reason"})
        .sort_values(["rows", "exclusion_reason"], ascending=[False, True], kind="mergesort")
    )

    summary = {
        "schema_version": "1.0",
        "profile_id": str(contract.get("profile_id", "") or ""),
        "contract_id": str(contract.get("contract_id", "") or ""),
        "lock_version": str(contract.get("sample_id_lock", {}).get("lock_version", "") or ""),
        "cohort_hash": str(contract.get("sample_id_lock", {}).get("cohort_hash", "") or ""),
        "taxonomy_hash": str(contract.get("sample_id_lock", {}).get("taxonomy_hash", "") or ""),
        "locked_sample_count": int(len(lock_ids)),
        "current_governed_sample_count": int(len(current_ids)),
        "full_catalog_sample_count": int(len(catalog_ids)),
        "locked_current_overlap_count": int(len(lock_ids & current_ids)),
        "locked_missing_from_current_count": int(len(lock_ids - current_ids)),
        "current_governed_missing_from_lock_count": int(len(current_ids - lock_ids)),
        "full_catalog_excluded_from_current_count": int(len(catalog_ids - current_ids)),
        "locked_rows_now_failing_time_window_count": int(
            (locked_failures["current_gate_reason"] == "outside_time_window").sum()
        ),
        "locked_member_list_hash": hash_payload(sorted(lock_ids)),
    }
    return {
        "summary": summary,
        "locked_vs_current_overlap": overlap.sort_values("sample_id", kind="mergesort"),
        "governed_missing_from_lock_by_family": by_family,
        "governed_missing_from_lock_by_source_batch": by_source,
        "catalog_exclusion_reasons": exclusion_counts,
        "locked_rows_now_failing_current_gates": locked_failures.sort_values("sample_id", kind="mergesort"),
    }


def write_cohort_gap_artifacts(*, output_dir: Path, audit: dict[str, Any]) -> dict[str, str]:
    """Write the full cohort gap audit bundle."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "locked_vs_current_overlap": output_dir / "locked_vs_current_overlap.csv",
        "governed_missing_from_lock_by_family": output_dir / "governed_missing_from_lock_by_family.csv",
        "governed_missing_from_lock_by_source_batch": output_dir / "governed_missing_from_lock_by_source_batch.csv",
        "catalog_exclusion_reasons": output_dir / "catalog_exclusion_reasons.csv",
        "locked_rows_now_failing_current_gates": output_dir / "locked_rows_now_failing_current_gates.csv",
        "cohort_gap_summary": output_dir / "cohort_gap_summary.json",
        "cohort_gap_report": output_dir / "cohort_gap_report.md",
    }
    for key, path in paths.items():
        if key in {"cohort_gap_summary", "cohort_gap_report"}:
            continue
        df = audit[key]
        assert isinstance(df, pd.DataFrame)
        df.to_csv(path, index=False)
    summary = audit["summary"]
    paths["cohort_gap_summary"].write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_lines = [
        "# Cohort Gap Report",
        "",
        f"- Locked sample count: **{summary['locked_sample_count']}**",
        f"- Current governed Android APK rows: **{summary['current_governed_sample_count']}**",
        f"- Full Android APK catalog rows: **{summary['full_catalog_sample_count']}**",
        f"- Locked/current overlap: **{summary['locked_current_overlap_count']}**",
        f"- Locked rows excluded by current live gates: **{summary['locked_missing_from_current_count']}**",
        f"- Current governed rows missing from lock: **{summary['current_governed_missing_from_lock_count']}**",
        f"- Locked rows failing current time window: **{summary['locked_rows_now_failing_time_window_count']}**",
        "",
        "## Core hashes",
        "",
        f"- cohort_hash: `{summary['cohort_hash']}`",
        f"- taxonomy_hash: `{summary['taxonomy_hash']}`",
        f"- member_list_hash: `{summary['locked_member_list_hash']}`",
        "",
        "## Exports",
        "",
        "- `locked_vs_current_overlap.csv`",
        "- `governed_missing_from_lock_by_family.csv`",
        "- `governed_missing_from_lock_by_source_batch.csv`",
        "- `catalog_exclusion_reasons.csv`",
        "- `locked_rows_now_failing_current_gates.csv`",
    ]
    paths["cohort_gap_report"].write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return {key: str(path) for key, path in paths.items()}
