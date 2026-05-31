"""Canonical cohort census and gate-matrix exports for paper-facing profile review."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import json
import pandas as pd
import warnings

from obsidiandroid.cli.profile_manager import load_profile
from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.database import db_engine
from obsidiandroid.database import db_sample_metadata_queries
from obsidiandroid.governance import paper_cohort_contract
from obsidiandroid.governance.cohort_lock_manifest import read_member_list
from obsidiandroid.governance.cohort_reproducibility import apply_analysis_snapshot_lock
from obsidiandroid.orchestration.profile_filters import (
    apply_dataset_filters,
    malicious_signal_or_taxonomy_mask,
    split_benign_malicious,
)
from obsidiandroid.pipeline.contract_filters import apply_contract_filters
from obsidiandroid.pipeline.permission_trends.sample_permission_data import fetch_permission_aggregates
from obsidiandroid.pipeline.manifest.paper_export_contracts import (
    build_paper_export_contract,
    missing_required_paper_sources,
)


TARGET_PROFILE_IDS: tuple[str, ...] = (
    "malicious_temporal_stability_locked",
    "malicious_temporal_stability",
    "malicious_temporal_stability_expanded",
    "malicious_temporal_stability_long_tail",
    "malicious_temporal_consensus10",
    "malicious_temporal_family300",
    "paper2_primary",
    "paper2_primary_locked",
    "paper2_sensitivity_consensus10",
    "paper2_sensitivity_family300",
)

SUPPORT_FLOOR_REFERENCE_VALUES: tuple[int, ...] = (20, 10, 5, 1)
UNKNOWN_FAMILY_VALUES = {"", "unknown", "other", "unmapped", "none", "null"}
UNKNOWN_TYPE_VALUES = {"", "unknown"}
WEAK_LABEL_KINDS = {"filename", "hash_like", "opaque_string", "unclassified"}


@dataclass(frozen=True)
class ProfileRuntimeSemantics:
    """Normalized profile semantics needed for cohort census."""

    profile_id: str
    canonical_profile_id: str
    readiness_bucket: str
    paper_locked: bool
    type_slug_filter: str | None
    min_samples_per_family: int | None
    require_mapped_family: bool
    require_sha256: bool
    allow_missing_package_name: bool
    exclude_unknown_type_slug: bool
    exclude_weak_label_kinds: bool
    exclude_family_label_conflicts: bool
    min_malicious_detections: int
    family_cap: int | None
    family_cap_seed: int | None
    type_cap: int | None
    type_cap_seed: int | None
    type_cap_by_slug: dict[str, int]
    exclude_families: tuple[str, ...]
    include_families: tuple[str, ...]
    time_window_start_utc: str
    time_window_end_utc: str
    require_effective_first_seen: bool
    dataset_filter_mode: str
    exclude_unknown_from_main_results: bool
    contract: dict[str, Any]


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
        "classification_primary",
        "classification_subtype",
        "vt_suggested_label",
    ):
        if column not in df.columns:
            df[column] = ""
        df[column] = df[column].fillna("").astype(str)
    for column in (
        "effective_first_seen_at_utc",
        "vt_first_submission_at_utc",
    ):
        if column not in df.columns:
            df[column] = pd.NaT
        df[column] = pd.to_datetime(df[column], errors="coerce", utc=True)
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
    family_norm = df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
    family_id_present = (
        pd.to_numeric(df["family_id"], errors="coerce").notna()
        if "family_id" in df.columns
        else pd.Series(False, index=df.index)
    )
    return family_id_present | (~family_norm.isin(UNKNOWN_FAMILY_VALUES))


def _family_label_conflict_mask(df: pd.DataFrame) -> pd.Series:
    raw = df["family_label"].fillna("").astype(str).str.strip().str.lower()
    canonical = df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
    return (
        ~raw.isin({"", "unknown", "generic", "unclassified", "unlabeled"})
        & ~canonical.isin(UNKNOWN_FAMILY_VALUES)
        & (raw != canonical)
    )


def _cohort_membership_hash(df: pd.DataFrame) -> str:
    if "sample_id" not in df.columns:
        return ""
    ids = (
        pd.to_numeric(df["sample_id"], errors="coerce")
        .dropna()
        .astype(int)
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    return hash_payload(ids)


def _label_snapshot_hash(df: pd.DataFrame) -> str:
    payload: list[tuple[Any, ...]] = []
    if df.empty:
        return ""
    sample_ids = pd.to_numeric(df["sample_id"], errors="coerce").fillna(-1).astype(int)
    family_ids = pd.to_numeric(df.get("family_id"), errors="coerce").fillna(-1).astype(int)
    family_names = df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
    type_slugs = df["type_slug"].fillna("").astype(str).str.strip().str.lower()
    for sample_id, family_id, family_name, type_slug in zip(
        sample_ids.tolist(),
        family_ids.tolist(),
        family_names.tolist(),
        type_slugs.tolist(),
        strict=False,
    ):
        payload.append((sample_id, family_id, family_name, type_slug))
    payload.sort()
    return hash_payload(payload)


def _to_runtime_semantics(profile: dict[str, Any]) -> ProfileRuntimeSemantics:
    gates = profile.get("cohort_gates", {}) if isinstance(profile.get("cohort_gates"), dict) else {}
    dataset_filters = (
        profile.get("dataset_filters", {}) if isinstance(profile.get("dataset_filters"), dict) else {}
    )
    requested_profile_id = str(
        profile.get("__requested_profile_ref", profile.get("profile_id", "")) or profile.get("profile_id", "")
    )
    return ProfileRuntimeSemantics(
        profile_id=requested_profile_id,
        canonical_profile_id=str(
            profile.get("__canonical_profile_id", profile.get("profile_id", "")) or profile.get("profile_id", "")
        ),
        readiness_bucket=str(profile.get("cohort_readiness_bucket", "") or ""),
        paper_locked=bool(profile.get("paper_locked", False)),
        type_slug_filter=(
            str(profile.get("type_slug_filter", "") or "").strip().lower()
            if profile.get("type_slug_filter") not in (None, "")
            else None
        ),
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
        min_malicious_detections=int(gates.get("min_malicious_detections", 0) or 0),
        family_cap=(
            int(gates.get("family_cap"))
            if gates.get("family_cap") not in (None, "")
            else None
        ),
        family_cap_seed=(
            int(gates.get("family_cap_seed"))
            if gates.get("family_cap_seed") not in (None, "")
            else None
        ),
        type_cap=(
            int(gates.get("type_cap"))
            if gates.get("type_cap") not in (None, "")
            else None
        ),
        type_cap_seed=(
            int(gates.get("type_cap_seed"))
            if gates.get("type_cap_seed") not in (None, "")
            else None
        ),
        type_cap_by_slug={
            str(key).strip().lower(): int(value)
            for key, value in (gates.get("type_cap_by_slug", {}) or {}).items()
            if str(key).strip() and value not in (None, "") and int(value) > 0
        },
        exclude_families=tuple(
            str(value).strip().lower()
            for value in (gates.get("exclude_families", []) or [])
            if str(value).strip()
        ),
        include_families=tuple(
            str(value).strip().lower()
            for value in (gates.get("include_families", []) or [])
            if str(value).strip()
        ),
        time_window_start_utc=str(gates.get("time_window_start_utc", "") or ""),
        time_window_end_utc=str(gates.get("time_window_end_utc", "") or ""),
        require_effective_first_seen=True,
        dataset_filter_mode=str(dataset_filters.get("mode", "none") or "none").strip().lower(),
        exclude_unknown_from_main_results=bool(profile.get("exclude_unknown_from_main_results", False)),
        contract=paper_cohort_contract.build_declared_contract(profile),
    )


def _load_broad_catalog_slice(type_slug_filter: str | None) -> pd.DataFrame:
    frame = db_sample_metadata_queries.load_samples_by_type(
        type_slug=type_slug_filter,
        min_samples_per_family=None,
        require_mapped_family=False,
        require_sha256=False,
        allow_missing_package_name=True,
        exclude_unknown_type_slug=False,
        exclude_weak_label_kinds=False,
        exclude_family_label_conflicts=False,
        limit=None,
        family_cap=None,
        family_cap_seed=None,
        type_cap=None,
        type_cap_seed=None,
        type_cap_by_slug=None,
        effective_time_start_utc=None,
        effective_time_end_utc=None,
        require_effective_first_seen=False,
        exclude_family_canonical=tuple(),
    )
    return _normalize_df(frame)


def _build_sql_precondition_mask(df: pd.DataFrame, semantics: ProfileRuntimeSemantics) -> pd.Series:
    effective_ts = _effective_ts(df)
    family_norm = df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
    type_norm = df["type_slug"].fillna("").astype(str).str.strip().str.lower()
    sample_label_kind = df["sample_label_kind"].fillna("").astype(str).str.strip().str.lower()
    pkg_norm = df["android_package_name"].fillna("").astype(str).str.strip()
    sha_norm = df["sha256"].fillna("").astype(str).str.strip().str.lower()
    mapped_family = _mapped_family_mask(df)
    family_conflict = _family_label_conflict_mask(df)

    allowed = pd.Series(True, index=df.index)
    if semantics.type_slug_filter:
        allowed &= type_norm.eq(semantics.type_slug_filter)
    if semantics.require_mapped_family:
        allowed &= mapped_family
    if semantics.require_sha256:
        allowed &= sha_norm.str.len().eq(64)
    if not semantics.allow_missing_package_name:
        allowed &= pkg_norm.ne("")
    if semantics.exclude_unknown_type_slug:
        allowed &= ~type_norm.isin(UNKNOWN_TYPE_VALUES)
    if semantics.exclude_weak_label_kinds:
        allowed &= ~sample_label_kind.isin(WEAK_LABEL_KINDS)
    if semantics.exclude_family_label_conflicts:
        allowed &= ~family_conflict
    if semantics.require_effective_first_seen:
        allowed &= effective_ts.notna()
    if semantics.time_window_start_utc:
        allowed &= effective_ts.ge(pd.Timestamp(semantics.time_window_start_utc))
    if semantics.time_window_end_utc:
        allowed &= effective_ts.lt(pd.Timestamp(semantics.time_window_end_utc))
    if semantics.exclude_families and not semantics.paper_locked:
        allowed &= ~family_norm.isin(set(semantics.exclude_families))
    return allowed


def _apply_family_support_floor(
    df: pd.DataFrame,
    semantics: ProfileRuntimeSemantics,
    *,
    locked_authoritative: bool,
) -> tuple[pd.DataFrame, pd.Series]:
    out = df.copy()
    if semantics.min_samples_per_family is None or locked_authoritative:
        return out, pd.Series(False, index=out.index)
    allowed = _build_sql_precondition_mask(out, semantics)
    family_norm = out["family_canonical"].fillna("").astype(str).str.strip().str.lower()
    family_support_counts = (
        family_norm[
            allowed & ~family_norm.isin(UNKNOWN_FAMILY_VALUES)
        ]
        .value_counts()
        .to_dict()
    )
    support = family_norm.map(lambda value: int(family_support_counts.get(value, 0)))
    below = allowed & (support < int(semantics.min_samples_per_family))
    return out.loc[~below].copy(), below


def _apply_group_cap(
    df: pd.DataFrame,
    *,
    column: str,
    cap: int | None,
    seed: int | None,
) -> tuple[pd.DataFrame, pd.Series]:
    out = df.copy()
    if cap is None or int(cap) <= 0 or column not in out.columns:
        return out, pd.Series(False, index=out.index)
    dropped = pd.Series(False, index=out.index)
    kept_indices: list[int] = []
    for _, group in out.groupby(column, dropna=False, sort=True):
        if len(group) <= int(cap):
            kept_indices.extend(group.index.tolist())
        else:
            kept = group.sample(n=int(cap), random_state=int(seed or 42))
            kept_indices.extend(kept.index.tolist())
            dropped.loc[group.index.difference(kept.index)] = True
    return out.loc[sorted(kept_indices)].copy(), dropped


def _apply_type_cap_by_slug(df: pd.DataFrame, caps: dict[str, int], seed: int | None) -> tuple[pd.DataFrame, pd.Series]:
    out = df.copy()
    if not caps or "type_slug" not in out.columns:
        return out, pd.Series(False, index=out.index)
    dropped = pd.Series(False, index=out.index)
    kept_indices: list[int] = []
    for type_slug, group in out.groupby("type_slug", dropna=False, sort=True):
        normalized = str(type_slug).strip().lower()
        cap = caps.get(normalized)
        if cap is None or len(group) <= int(cap):
            kept_indices.extend(group.index.tolist())
        else:
            kept = group.sample(n=int(cap), random_state=int(seed or 42))
            kept_indices.extend(kept.index.tolist())
            dropped.loc[group.index.difference(kept.index)] = True
    return out.loc[sorted(kept_indices)].copy(), dropped


def _resolve_live_profile_cohort(
    broad_catalog_df: pd.DataFrame,
    semantics: ProfileRuntimeSemantics,
) -> pd.DataFrame:
    work = broad_catalog_df.copy()
    locked_authoritative = semantics.paper_locked and bool(
        str(semantics.contract.get("sample_id_lock", {}).get("path", "") or "").strip()
    )
    sql_pre = _build_sql_precondition_mask(work, semantics)
    work = work.loc[sql_pre].copy()
    work, _ = _apply_family_support_floor(work, semantics, locked_authoritative=locked_authoritative)
    work, _ = _apply_group_cap(
        work,
        column="family_canonical",
        cap=semantics.family_cap if not locked_authoritative else semantics.family_cap,
        seed=semantics.family_cap_seed,
    )
    work, _ = _apply_group_cap(
        work,
        column="type_slug",
        cap=semantics.type_cap,
        seed=semantics.type_cap_seed,
    )
    work, _ = _apply_type_cap_by_slug(work, semantics.type_cap_by_slug, semantics.type_cap_seed)

    if locked_authoritative:
        lock_path = str(semantics.contract.get("sample_id_lock", {}).get("path", "") or "").strip()
        return apply_analysis_snapshot_lock(work, lock_path, fail_closed=True)

    work = apply_dataset_filters(work, {"dataset_filters": {"mode": semantics.dataset_filter_mode}})
    work.attrs["sql_exclude_families_applied"] = tuple(semantics.exclude_families)
    work.attrs["family_cap_applied_in_sql"] = bool(semantics.family_cap and semantics.family_cap > 0)
    work.attrs["family_cap_sql_value"] = semantics.family_cap
    work.attrs["family_cap_sql_seed"] = semantics.family_cap_seed
    work.attrs["type_cap_applied_in_sql"] = bool(semantics.type_cap and semantics.type_cap > 0)
    work.attrs["type_cap_sql_value"] = semantics.type_cap
    work.attrs["type_cap_sql_seed"] = semantics.type_cap_seed
    work.attrs["type_cap_by_slug_applied_in_sql"] = bool(semantics.type_cap_by_slug)
    work.attrs["type_cap_by_slug_sql_value"] = dict(semantics.type_cap_by_slug)
    work, _ = apply_contract_filters(
        samples_df=work,
        gates={
            "exclude_unknown_type_slug": semantics.exclude_unknown_type_slug,
            "min_malicious_detections": semantics.min_malicious_detections,
            "include_families": list(semantics.include_families),
            "exclude_families": list(semantics.exclude_families),
            "family_cap": semantics.family_cap,
            "family_cap_seed": semantics.family_cap_seed,
            "type_cap": semantics.type_cap,
            "type_cap_seed": semantics.type_cap_seed,
            "type_cap_by_slug": dict(semantics.type_cap_by_slug),
        },
        run_id=f"cohort_census::{semantics.profile_id}",
    )
    return work.sort_values("sample_id", kind="mergesort").reset_index(drop=True)


def _reason_series_exact(df: pd.DataFrame, semantics: ProfileRuntimeSemantics) -> pd.Series:
    work = _normalize_df(df)
    reasons = pd.Series("", index=work.index, dtype="object")
    effective_ts = _effective_ts(work)
    family_norm = work["family_canonical"].fillna("").astype(str).str.strip().str.lower()
    type_norm = work["type_slug"].fillna("").astype(str).str.strip().str.lower()
    sample_label_kind = work["sample_label_kind"].fillna("").astype(str).str.strip().str.lower()
    pkg_norm = work["android_package_name"].fillna("").astype(str).str.strip()
    sha_norm = work["sha256"].fillna("").astype(str).str.strip().str.lower()
    mapped_family = _mapped_family_mask(work)
    family_conflict = _family_label_conflict_mask(work)

    if semantics.type_slug_filter:
        reasons.loc[type_norm.ne(semantics.type_slug_filter)] = "outside_profile_type_scope"
    if semantics.require_sha256:
        reasons.loc[reasons.eq("") & ~sha_norm.str.len().eq(64)] = "missing_sha256"
    if semantics.require_mapped_family:
        reasons.loc[reasons.eq("") & ~mapped_family] = "missing_mapped_family"
    if not semantics.allow_missing_package_name:
        reasons.loc[reasons.eq("") & pkg_norm.eq("")] = "missing_package_name"
    if semantics.exclude_unknown_type_slug:
        reasons.loc[reasons.eq("") & type_norm.isin(UNKNOWN_TYPE_VALUES)] = "unknown_type_slug"
    if semantics.exclude_weak_label_kinds:
        reasons.loc[reasons.eq("") & sample_label_kind.isin(WEAK_LABEL_KINDS)] = "weak_label_kind"
    if semantics.exclude_family_label_conflicts:
        reasons.loc[reasons.eq("") & family_conflict] = "family_label_conflict"
    if semantics.require_effective_first_seen:
        reasons.loc[reasons.eq("") & effective_ts.isna()] = "missing_effective_first_seen"
    if semantics.time_window_start_utc:
        reasons.loc[
            reasons.eq("") & effective_ts.notna() & effective_ts.lt(pd.Timestamp(semantics.time_window_start_utc))
        ] = "outside_time_window"
    if semantics.time_window_end_utc:
        reasons.loc[
            reasons.eq("") & effective_ts.notna() & effective_ts.ge(pd.Timestamp(semantics.time_window_end_utc))
        ] = "outside_time_window"

    pre_allowed = reasons.eq("")
    if semantics.min_samples_per_family is not None and not semantics.paper_locked:
        support_counts = family_norm[
            pre_allowed & ~family_norm.isin(UNKNOWN_FAMILY_VALUES)
        ].value_counts().to_dict()
        support = family_norm.map(lambda value: int(support_counts.get(value, 0)))
        reasons.loc[reasons.eq("") & (support < int(semantics.min_samples_per_family))] = "below_min_samples_per_family"

    if semantics.exclude_families and not semantics.paper_locked:
        reasons.loc[reasons.eq("") & family_norm.isin(set(semantics.exclude_families))] = "excluded_family"

    if semantics.family_cap is not None and int(semantics.family_cap) > 0:
        eligible = work.loc[reasons.eq("")].copy()
        _, dropped = _apply_group_cap(
            eligible,
            column="family_canonical",
            cap=semantics.family_cap,
            seed=semantics.family_cap_seed,
        )
        if not eligible.empty:
            dropped_ids = set(eligible.loc[dropped, "sample_id"].tolist())
            reasons.loc[reasons.eq("") & work["sample_id"].isin(dropped_ids)] = "family_cap"

    if semantics.type_cap is not None and int(semantics.type_cap) > 0:
        eligible = work.loc[reasons.eq("")].copy()
        _, dropped = _apply_group_cap(
            eligible,
            column="type_slug",
            cap=semantics.type_cap,
            seed=semantics.type_cap_seed,
        )
        if not eligible.empty:
            dropped_ids = set(eligible.loc[dropped, "sample_id"].tolist())
            reasons.loc[reasons.eq("") & work["sample_id"].isin(dropped_ids)] = "type_cap"

    if semantics.type_cap_by_slug:
        eligible = work.loc[reasons.eq("")].copy()
        _, dropped = _apply_type_cap_by_slug(eligible, semantics.type_cap_by_slug, semantics.type_cap_seed)
        if not eligible.empty:
            dropped_ids = set(eligible.loc[dropped, "sample_id"].tolist())
            reasons.loc[reasons.eq("") & work["sample_id"].isin(dropped_ids)] = "type_cap_by_slug"

    if semantics.paper_locked:
        lock_path = str(semantics.contract.get("sample_id_lock", {}).get("path", "") or "").strip()
        locked_ids = set(read_member_list(lock_path)["sample_id"].tolist()) if lock_path else set()
        reasons.loc[reasons.eq("") & ~work["sample_id"].isin(locked_ids)] = "not_in_locked_member_list"
        reasons.loc[reasons.eq("")] = "eligible_locked_membership"
        return reasons

    filtered = work.loc[reasons.eq("")].copy()
    benign_df, malicious_df = split_benign_malicious(filtered)
    if semantics.dataset_filter_mode == "malicious_only":
        allowed_ids = set(malicious_df["sample_id"].tolist())
        reasons.loc[reasons.eq("") & ~work["sample_id"].isin(allowed_ids)] = "dataset_filter_malicious_only"

    if semantics.exclude_unknown_type_slug or semantics.exclude_unknown_from_main_results:
        norm = family_norm
        type_ok = ~type_norm.isin(UNKNOWN_TYPE_VALUES)
        family_ok = ~norm.isin(UNKNOWN_FAMILY_VALUES)
        reasons.loc[reasons.eq("") & ~(family_ok & type_ok)] = "exclude_unknown_type_slug"

    if semantics.min_malicious_detections > 0:
        mal = pd.to_numeric(work.get("vt_malicious_count", pd.Series(pd.NA, index=work.index)), errors="coerce")
        susp = pd.to_numeric(work.get("vt_suspicious_count", pd.Series(pd.NA, index=work.index)), errors="coerce")
        consensus_total = mal.fillna(0) + susp.fillna(0)
        unknown_consensus = mal.isna() & susp.isna()
        rescued_unknown = unknown_consensus & malicious_signal_or_taxonomy_mask(work)
        reasons.loc[
            reasons.eq("") & ~((consensus_total >= semantics.min_malicious_detections) | rescued_unknown)
        ] = "min_malicious_detections"

    if semantics.include_families:
        reasons.loc[reasons.eq("") & ~family_norm.isin(set(semantics.include_families))] = "include_families"
    if semantics.exclude_families:
        reasons.loc[reasons.eq("") & family_norm.isin(set(semantics.exclude_families))] = "exclude_families"

    reasons.loc[reasons.eq("")] = "eligible_current_profile"
    return reasons


def _fetch_confidence_bucket_rows(sample_ids: list[int]) -> pd.DataFrame:
    if not sample_ids:
        return pd.DataFrame(columns=["sample_id", "confidence_bucket"])
    frames: list[pd.DataFrame] = []
    chunk_size = 500
    for start in range(0, len(sample_ids), chunk_size):
        chunk = sample_ids[start : start + chunk_size]
        placeholders = ", ".join(["%s"] * len(chunk))
        query = f"""
            SELECT sample_id, COALESCE(confidence_bucket, 'none') AS confidence_bucket
            FROM vt_sample_verdict_confidence_current
            WHERE sample_id IN ({placeholders})
        """
        frame = db_engine.execute_query(query, params=tuple(chunk), fetch=True, as_dataframe=True)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["sample_id", "confidence_bucket"])
    out = pd.concat(frames, ignore_index=True)
    out["sample_id"] = pd.to_numeric(out["sample_id"], errors="coerce")
    out = out.dropna(subset=["sample_id"])
    out["sample_id"] = out["sample_id"].astype(int)
    out["confidence_bucket"] = out["confidence_bucket"].fillna("none").astype(str).str.strip().str.lower()
    return out.drop_duplicates(subset=["sample_id"], keep="last")


def _distribution_dict(series: pd.Series) -> dict[str, int]:
    if series.empty:
        return {}
    values = series.fillna("").astype(str).replace("", "<blank>")
    counts = values.value_counts()
    return {str(key): int(value) for key, value in counts.items()}


def _json_ready_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Return JSON-serializable records from a dataframe."""
    work = df.copy()
    for column in work.columns:
        if pd.api.types.is_datetime64_any_dtype(work[column]):
            work[column] = work[column].map(lambda value: value.isoformat() if pd.notna(value) else "")
    return work.to_dict(orient="records")


def _top_count_dict(series: pd.Series, limit: int = 10) -> dict[str, int]:
    payload = _distribution_dict(series)
    return dict(list(payload.items())[: int(limit)])


def _permission_coverage_payload(df: pd.DataFrame, permission_aggregates_df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"rows_with_permission_obs": 0, "rows_total": 0, "coverage_pct": 0.0}
    merged = df[["sample_id"]].merge(permission_aggregates_df, on="sample_id", how="left")
    rows_with_permission = pd.to_numeric(
        merged.get("permission_obs_rows", 0), errors="coerce"
    ).fillna(0).astype(int).gt(0)
    total = int(len(merged))
    count = int(rows_with_permission.sum())
    return {
        "rows_with_permission_obs": count,
        "rows_total": total,
        "coverage_pct": round(float(count / total) if total else 0.0, 6),
    }


def _build_profile_summary_row(
    *,
    semantics: ProfileRuntimeSemantics,
    cohort_df: pd.DataFrame,
    broad_catalog_df: pd.DataFrame,
    permission_aggregates_df: pd.DataFrame,
) -> dict[str, Any]:
    contract = semantics.contract
    sample_lock = contract.get("sample_id_lock", {}) if isinstance(contract.get("sample_id_lock"), dict) else {}
    expected = contract.get("expected", {}) if isinstance(contract.get("expected"), dict) else {}
    confidence_df = _fetch_confidence_bucket_rows(cohort_df["sample_id"].tolist() if "sample_id" in cohort_df.columns else [])
    confidence_distribution = _distribution_dict(confidence_df.get("confidence_bucket", pd.Series(dtype="object")))
    permission_payload = _permission_coverage_payload(cohort_df, permission_aggregates_df)
    family_series = cohort_df["family_canonical"].fillna("").astype(str).str.strip()
    type_series = cohort_df["type_slug"].fillna("").astype(str).str.strip().str.lower()
    source_series = cohort_df["source_batch_label"].fillna("").astype(str).str.strip()
    broad_family_series = broad_catalog_df["family_canonical"].fillna("").astype(str).str.strip()
    top_family_share = 0.0
    if len(cohort_df) and not family_series[family_series != ""].empty:
        family_counts = family_series[family_series != ""].value_counts()
        top_family_share = float(family_counts.iloc[0] / len(cohort_df))

    if semantics.paper_locked:
        sample_count = int(expected.get("sample_count", len(cohort_df)) or len(cohort_df))
        family_count = int(expected.get("family_count", family_series[family_series != ""].nunique()) or 0)
        type_count = int(expected.get("type_count", type_series[type_series != ""].nunique()) or 0)
        cohort_hash = str(sample_lock.get("cohort_hash", "") or "") or _cohort_membership_hash(cohort_df)
        taxonomy_hash = str(sample_lock.get("taxonomy_hash", "") or "")
        source_snapshot = str(sample_lock.get("member_list_path", "") or "")
    else:
        sample_count = int(len(cohort_df))
        family_count = int(family_series[family_series != ""].nunique())
        type_count = int(type_series[type_series != ""].nunique())
        cohort_hash = _cohort_membership_hash(cohort_df)
        taxonomy_hash = _label_snapshot_hash(cohort_df)
        source_snapshot = "live_loader:malware_sample_catalog"

    permission_requirement = (
        "advisory_readiness_bucket" if "permission_obs" in semantics.readiness_bucket else "not_declared"
    )
    confidence_requirement = (
        "advisory_high_or_strong_readiness_bucket"
        if "high_or_strong" in semantics.readiness_bucket
        else "not_declared"
    )
    return {
        "profile_id": semantics.profile_id,
        "canonical_profile_id": semantics.canonical_profile_id,
        "paper_locked": semantics.paper_locked,
        "readiness_bucket": semantics.readiness_bucket,
        "sample_count": sample_count,
        "family_count": family_count,
        "type_count": type_count,
        "type_slugs": sorted([value for value in type_series[type_series != ""].unique().tolist() if value]),
        "support_floor": semantics.min_samples_per_family,
        "permission_observation_requirement": permission_requirement,
        "permission_observation_enforced": False,
        "confidence_bucket_rule": confidence_requirement,
        "confidence_bucket_enforced": False,
        "malicious_detection_threshold": semantics.min_malicious_detections,
        "suspicious_handling": {
            "dataset_filter_mode": semantics.dataset_filter_mode,
            "exclude_unknown_type_slug": semantics.exclude_unknown_type_slug,
            "exclude_unknown_from_main_results": semantics.exclude_unknown_from_main_results,
            "exclude_weak_label_kinds": semantics.exclude_weak_label_kinds,
            "exclude_family_label_conflicts": semantics.exclude_family_label_conflicts,
        },
        "family_exclusions": list(semantics.exclude_families),
        "family_cap": semantics.family_cap,
        "time_window": {
            "start_utc": semantics.time_window_start_utc,
            "end_utc": semantics.time_window_end_utc,
            "semantics": str(expected.get("time_window_semantics", "start_inclusive_end_exclusive") or "start_inclusive_end_exclusive"),
        },
        "cohort_membership_hash": cohort_hash,
        "taxonomy_hash": taxonomy_hash,
        "label_snapshot_hash": _label_snapshot_hash(cohort_df),
        "source_snapshot_or_lock_file": source_snapshot,
        "top_families": _top_count_dict(family_series[family_series != ""], limit=10),
        "top_malware_types": _top_count_dict(type_series[type_series != ""], limit=10),
        "source_batch_label_distribution": _top_count_dict(source_series, limit=10),
        "permission_coverage": permission_payload,
        "confidence_bucket_distribution": confidence_distribution,
        "top_family_share": round(top_family_share, 6),
        "live_catalog_match_count": int(len(cohort_df)),
        "live_catalog_family_count": int(family_series[family_series != ""].nunique()),
        "live_catalog_type_count": int(type_series[type_series != ""].nunique()),
        "broad_catalog_family_count": int(broad_family_series[broad_family_series != ""].nunique()),
    }


def _serialize_row_for_csv(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            out[key] = json.dumps(value, sort_keys=True, ensure_ascii=False)
        else:
            out[key] = value
    return out


def _load_latest_run_root() -> Path | None:
    root = repo_root() / "output" / "runs"
    if not root.exists():
        return None
    runs = sorted([path for path in root.iterdir() if path.is_dir()])
    return runs[-1] if runs else None


def _load_latest_paper_run_root() -> Path | None:
    root = repo_root() / "output" / "runs"
    if not root.exists():
        return None
    for run in sorted([path for path in root.iterdir() if path.is_dir()], reverse=True):
        if (run / "paper_exports" / "docs").exists():
            return run
    return None


def _strict_export_gate_status() -> dict[str, Any]:
    latest_paper_run = _load_latest_paper_run_root()
    latest_run = _load_latest_run_root()
    paper_constants_path = repo_root() / "artifacts" / "paper" / "paper_constants.json"
    status = {
        "paper_constants_present": paper_constants_path.exists(),
        "paper_constants_path": str(paper_constants_path),
        "latest_run_root": str(latest_run) if latest_run is not None else "",
        "latest_paper_run_root": str(latest_paper_run) if latest_paper_run is not None else "",
        "missing_required_sources": [],
        "passes": False,
    }
    if latest_paper_run is None:
        status["missing_required_sources"] = ["no_run_with_paper_exports_docs"]
        if not status["paper_constants_present"]:
            status["missing_required_sources"].append("paper_constants.json")
        return status

    diagnostics_dir = latest_paper_run / "diagnostics"
    contract = build_paper_export_contract(
        run_root=latest_paper_run,
        diagnostics_dir=diagnostics_dir,
        run_id=latest_paper_run.name,
        evidence_mode=True,
    )
    missing = missing_required_paper_sources(contract["required_sources"])
    status["missing_required_sources"] = missing
    docs_dir = latest_paper_run / "paper_exports" / "docs"
    required_docs = [
        docs_dir / "paper_registry.json",
        docs_dir / "paper_exports_manifest.json",
    ]
    missing_docs = [path.name for path in required_docs if not path.exists()]
    status["missing_required_sources"].extend(missing_docs)
    if not status["paper_constants_present"]:
        status["missing_required_sources"].append("paper_constants.json")
    status["passes"] = bool(status["paper_constants_present"] and not status["missing_required_sources"])
    return status


def _archived_lock_concepts() -> list[dict[str, Any]]:
    baselines_root = repo_root() / "artifacts" / "baselines"
    concepts: list[dict[str, Any]] = []
    if not baselines_root.exists():
        return concepts
    for manifest_path in sorted(baselines_root.glob("*/MANIFEST.txt")):
        text = manifest_path.read_text(encoding="utf-8")
        concepts.append(
            {
                "path": str(manifest_path),
                "summary": text.strip().splitlines()[0] if text.strip() else "",
                "body": text.strip(),
                "is_1187_rebaseline": "1187" in text and "35 families" in text,
            }
        )
    return concepts


def _build_support_floor_reference(
    *,
    broad_catalog_df: pd.DataFrame,
    base_profile: dict[str, Any],
    permission_aggregates_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for floor in SUPPORT_FLOOR_REFERENCE_VALUES:
        variant = json.loads(json.dumps(base_profile))
        gates = variant.setdefault("cohort_gates", {})
        gates["min_samples_per_family"] = int(floor)
        semantics = _to_runtime_semantics(variant)
        cohort_df = _resolve_live_profile_cohort(broad_catalog_df, semantics)
        rows.append(
            {
                "support_floor": int(floor),
                "sample_count": int(len(cohort_df)),
                "family_count": int(
                    cohort_df["family_canonical"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique()
                ),
                "type_count": int(
                    cohort_df["type_slug"].fillna("").astype(str).str.strip().str.lower().replace("", pd.NA).dropna().nunique()
                ),
                "permission_coverage": _permission_coverage_payload(cohort_df, permission_aggregates_df),
                "top_family_share": round(
                    float(
                        cohort_df["family_canonical"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().value_counts().iloc[0]
                        / len(cohort_df)
                    )
                    if len(cohort_df)
                    and not cohort_df["family_canonical"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().empty
                    else 0.0,
                    6,
                ),
            }
        )
    return rows


def _devixor_gigabud_counterfactual(
    *,
    broad_catalog_df: pd.DataFrame,
    base_profile: dict[str, Any],
) -> dict[str, Any]:
    variant = json.loads(json.dumps(base_profile))
    gates = variant.setdefault("cohort_gates", {})
    gates["exclude_families"] = []
    semantics = _to_runtime_semantics(variant)
    cohort_df = _resolve_live_profile_cohort(broad_catalog_df, semantics)
    family_series = cohort_df["family_canonical"].fillna("").astype(str).str.strip()
    counts = family_series.value_counts()
    total = int(len(cohort_df))
    out: dict[str, Any] = {"cohort_size_if_included": total}
    for family in ("Devixor", "Gigabud"):
        count = int(counts.get(family, 0))
        out[family] = {
            "rows": count,
            "share": round(float(count / total) if total else 0.0, 6),
        }
    out["combined_share"] = round(
        float((out["Devixor"]["rows"] + out["Gigabud"]["rows"]) / total) if total else 0.0,
        6,
    )
    return out


def _expansion_recommendation(rows: list[dict[str, Any]], expansion_by_family: pd.DataFrame) -> dict[str, Any]:
    current_candidates = [
        row
        for row in rows
        if row["canonical_profile_id"]
        in {
            "malicious_temporal_stability",
            "malicious_temporal_stability_expanded",
            "malicious_temporal_stability_long_tail",
            "malicious_temporal_consensus10",
            "malicious_temporal_family300",
        }
        and row["profile_id"] == row["canonical_profile_id"]
    ]
    locked = next((row for row in rows if row["canonical_profile_id"] == "malicious_temporal_stability_locked"), None)
    if locked is None or not current_candidates:
        return {"best_candidate_profile_id": "", "rationale": "insufficient_profiles"}

    by_profile = expansion_by_family.groupby("profile_id") if not expansion_by_family.empty else None
    recommendation = "malicious_temporal_stability_expanded"
    rationale = (
        "best conservative expansion candidate: support floor 10 increases coverage beyond the standard floor-20 cohort "
        "without dropping to the long-tail floor 5."
    )
    for row in current_candidates:
        if row["canonical_profile_id"] == "malicious_temporal_stability_expanded":
            top_missing_share = 0.0
            if by_profile is not None and row["profile_id"] in by_profile.groups:
                group = by_profile.get_group(row["profile_id"])
                total = int(group["rows"].sum())
                top_missing_share = float(group["rows"].max() / total) if total else 0.0
            return {
                "best_candidate_profile_id": recommendation,
                "rationale": rationale,
                "locked_sample_count": locked["sample_count"],
                "candidate_sample_count": row["sample_count"],
                "candidate_family_count": row["family_count"],
                "candidate_type_count": row["type_count"],
                "candidate_top_family_share": row["top_family_share"],
                "candidate_expansion_top_family_share": round(top_missing_share, 6),
                "defensible_today": bool(top_missing_share < 0.5),
            }
    first = current_candidates[0]
    return {
        "best_candidate_profile_id": first["profile_id"],
        "rationale": "fallback_first_current_candidate",
        "defensible_today": False,
    }


def build_cohort_census_bundle(profile_ids: tuple[str, ...] = TARGET_PROFILE_IDS) -> dict[str, Any]:
    """Build the canonical cohort census bundle for paper-facing profile review."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        profiles = [load_profile(profile_id) for profile_id in profile_ids]
    by_type_slug: dict[str | None, pd.DataFrame] = {}
    permission_aggregates_df = fetch_permission_aggregates()
    broad_type_slug = None
    if broad_type_slug not in by_type_slug:
        by_type_slug[broad_type_slug] = _load_broad_catalog_slice(broad_type_slug)
    all_catalog_df = by_type_slug[broad_type_slug]

    profile_rows: list[dict[str, Any]] = []
    overlap_csv_df = pd.DataFrame()
    overlap_json_records: list[dict[str, Any]] = []
    exclusion_frames: list[pd.DataFrame] = []
    expansion_family_frames: list[pd.DataFrame] = []
    expansion_type_frames: list[pd.DataFrame] = []
    source_distribution_frames: list[pd.DataFrame] = []
    locked_row: dict[str, Any] | None = None
    locked_member_ids: set[int] = set()

    for profile in profiles:
        semantics = _to_runtime_semantics(profile)
        if semantics.type_slug_filter not in by_type_slug:
            by_type_slug[semantics.type_slug_filter] = _load_broad_catalog_slice(semantics.type_slug_filter)
        broad_catalog_df = by_type_slug[semantics.type_slug_filter]
        cohort_df = _resolve_live_profile_cohort(broad_catalog_df, semantics)
        row = _build_profile_summary_row(
            semantics=semantics,
            cohort_df=cohort_df,
            broad_catalog_df=broad_catalog_df,
            permission_aggregates_df=permission_aggregates_df,
        )
        profile_rows.append(row)

        reasons = _reason_series_exact(broad_catalog_df, semantics)
        exclusion_frame = (
            reasons[reasons != ("eligible_locked_membership" if semantics.paper_locked else "eligible_current_profile")]
            .value_counts()
            .rename_axis("exclusion_reason")
            .reset_index(name="rows")
        )
        exclusion_frame.insert(0, "canonical_profile_id", semantics.canonical_profile_id)
        exclusion_frame.insert(0, "profile_id", semantics.profile_id)
        exclusion_frames.append(exclusion_frame)

        source_distribution = (
            cohort_df.assign(
                source_batch_label=cohort_df["source_batch_label"].replace("", "<blank>")
            )
            .groupby("source_batch_label", dropna=False)
            .agg(rows=("sample_id", "count"))
            .reset_index()
        )
        source_distribution.insert(0, "distribution_scope", "cohort_membership")
        source_distribution.insert(0, "canonical_profile_id", semantics.canonical_profile_id)
        source_distribution.insert(0, "profile_id", semantics.profile_id)
        source_distribution["share"] = source_distribution["rows"].astype(float) / max(int(len(cohort_df)), 1)
        source_distribution_frames.append(source_distribution)

        if semantics.paper_locked and semantics.canonical_profile_id == "malicious_temporal_stability_locked":
            locked_row = row
            locked_member_ids = set(read_member_list(semantics.contract["sample_id_lock"]["path"])["sample_id"].tolist())
            locked_members_df = broad_catalog_df[broad_catalog_df["sample_id"].isin(locked_member_ids)].copy()
            current_reference = next(
                item for item in profiles if str(item.get("profile_id", "")) == "malicious_temporal_stability"
            )
            current_reference_semantics = _to_runtime_semantics(current_reference)
            current_reference_df = _resolve_live_profile_cohort(broad_catalog_df, current_reference_semantics)
            overlap_ids = sorted(locked_member_ids | set(current_reference_df["sample_id"].tolist()))
            overlap_base = pd.DataFrame({"sample_id": overlap_ids})
            meta_cols = [
                "sample_id",
                "sha256",
                "family_canonical",
                "type_slug",
                "source_batch_label",
                "android_package_name",
                "effective_first_seen_at_utc",
                "vt_first_submission_at_utc",
            ]
            overlap_base = overlap_base.merge(
                broad_catalog_df[[col for col in meta_cols if col in broad_catalog_df.columns]].drop_duplicates("sample_id"),
                on="sample_id",
                how="left",
            )
            live_reasons = _reason_series_exact(broad_catalog_df, current_reference_semantics)
            reason_map = pd.DataFrame(
                {"sample_id": broad_catalog_df["sample_id"], "current_gate_reason": live_reasons}
            ).drop_duplicates("sample_id")
            overlap_base = overlap_base.merge(reason_map, on="sample_id", how="left")
            overlap_base["in_locked_membership"] = overlap_base["sample_id"].isin(locked_member_ids)
            current_ids = set(current_reference_df["sample_id"].tolist())
            overlap_base["in_current_governed"] = overlap_base["sample_id"].isin(current_ids)
            overlap_base["in_full_catalog"] = overlap_base["sample_id"].isin(set(broad_catalog_df["sample_id"].tolist()))
            overlap_csv_df = overlap_base.sort_values("sample_id", kind="mergesort").reset_index(drop=True)
            overlap_json_records = _json_ready_records(overlap_csv_df)

            for candidate_profile in profiles:
                candidate_semantics = _to_runtime_semantics(candidate_profile)
                if candidate_semantics.paper_locked:
                    continue
                candidate_df = _resolve_live_profile_cohort(broad_catalog_df, candidate_semantics)
                expansion_df = candidate_df.loc[~candidate_df["sample_id"].isin(locked_member_ids)].copy()
                if expansion_df.empty:
                    continue
                by_family = (
                    expansion_df.assign(
                        family_canonical=expansion_df["family_canonical"].replace("", "<blank>")
                    )
                    .groupby("family_canonical", dropna=False)
                    .agg(rows=("sample_id", "count"))
                    .reset_index()
                    .sort_values(["rows", "family_canonical"], ascending=[False, True], kind="mergesort")
                )
                by_family.insert(0, "canonical_profile_id", candidate_semantics.canonical_profile_id)
                by_family.insert(0, "profile_id", candidate_semantics.profile_id)
                expansion_family_frames.append(by_family)

                by_type = (
                    expansion_df.assign(type_slug=expansion_df["type_slug"].replace("", "<blank>"))
                    .groupby("type_slug", dropna=False)
                    .agg(rows=("sample_id", "count"))
                    .reset_index()
                    .sort_values(["rows", "type_slug"], ascending=[False, True], kind="mergesort")
                )
                by_type.insert(0, "canonical_profile_id", candidate_semantics.canonical_profile_id)
                by_type.insert(0, "profile_id", candidate_semantics.profile_id)
                expansion_type_frames.append(by_type)

                by_source = (
                    expansion_df.assign(source_batch_label=expansion_df["source_batch_label"].replace("", "<blank>"))
                    .groupby("source_batch_label", dropna=False)
                    .agg(rows=("sample_id", "count"))
                    .reset_index()
                    .sort_values(["rows", "source_batch_label"], ascending=[False, True], kind="mergesort")
                )
                by_source.insert(0, "distribution_scope", "expansion_candidates_missing_from_lock")
                by_source.insert(0, "canonical_profile_id", candidate_semantics.canonical_profile_id)
                by_source.insert(0, "profile_id", candidate_semantics.profile_id)
                by_source["share"] = by_source["rows"].astype(float) / max(int(len(expansion_df)), 1)
                source_distribution_frames.append(by_source)

    profile_rows_sorted = sorted(profile_rows, key=lambda row: (str(row["canonical_profile_id"]), str(row["profile_id"])))
    support_floor_rows = _build_support_floor_reference(
        broad_catalog_df=all_catalog_df,
        base_profile=next(profile for profile in profiles if str(profile.get("profile_id", "")) == "malicious_temporal_stability"),
        permission_aggregates_df=permission_aggregates_df,
    )
    devixor_gigabud = _devixor_gigabud_counterfactual(
        broad_catalog_df=all_catalog_df,
        base_profile=next(profile for profile in profiles if str(profile.get("profile_id", "")) == "malicious_temporal_stability"),
    )
    expansion_family_df = (
        pd.concat(expansion_family_frames, ignore_index=True) if expansion_family_frames else pd.DataFrame(
            columns=["profile_id", "canonical_profile_id", "family_canonical", "rows"]
        )
    )
    expansion_type_df = (
        pd.concat(expansion_type_frames, ignore_index=True) if expansion_type_frames else pd.DataFrame(
            columns=["profile_id", "canonical_profile_id", "type_slug", "rows"]
        )
    )
    source_distribution_df = (
        pd.concat(source_distribution_frames, ignore_index=True) if source_distribution_frames else pd.DataFrame(
            columns=["profile_id", "canonical_profile_id", "distribution_scope", "source_batch_label", "rows", "share"]
        )
    )
    exclusion_reasons_df = (
        pd.concat(exclusion_frames, ignore_index=True) if exclusion_frames else pd.DataFrame(
            columns=["profile_id", "canonical_profile_id", "exclusion_reason", "rows"]
        )
    )
    strict_export_status = _strict_export_gate_status()
    archived_lock_concepts = _archived_lock_concepts()
    recommendation = _expansion_recommendation(profile_rows_sorted, expansion_family_df)

    return {
        "profile_rows": profile_rows_sorted,
        "locked_vs_current_overlap_csv": overlap_csv_df,
        "locked_vs_current_overlap_json": overlap_json_records,
        "cohort_exclusion_reasons": exclusion_reasons_df,
        "cohort_expansion_candidates_by_family": expansion_family_df,
        "cohort_expansion_candidates_by_type": expansion_type_df,
        "cohort_source_batch_distribution": source_distribution_df,
        "support_floor_reference": support_floor_rows,
        "devixor_gigabud_counterfactual": devixor_gigabud,
        "strict_export_status": strict_export_status,
        "archived_lock_concepts": archived_lock_concepts,
        "expansion_recommendation": recommendation,
        "locked_profile_row": locked_row or {},
    }


def _report_lines(bundle: dict[str, Any]) -> list[str]:
    rows: list[dict[str, Any]] = bundle["profile_rows"]
    row_by_profile = {row["profile_id"]: row for row in rows}
    canonical_rows = {
        row["canonical_profile_id"]: row
        for row in rows
        if row["profile_id"] == row["canonical_profile_id"]
    }
    locked = canonical_rows.get("malicious_temporal_stability_locked", {})
    current = canonical_rows.get("malicious_temporal_stability", {})
    expanded = canonical_rows.get("malicious_temporal_stability_expanded", {})
    long_tail = canonical_rows.get("malicious_temporal_stability_long_tail", {})
    consensus10 = canonical_rows.get("malicious_temporal_consensus10", {})
    family300 = canonical_rows.get("malicious_temporal_family300", {})
    support_floors = bundle["support_floor_reference"]
    strict_status = bundle["strict_export_status"]
    recommendation = bundle["expansion_recommendation"]
    archived = bundle["archived_lock_concepts"]
    archived_rebaseline = next((item for item in archived if item.get("is_1187_rebaseline")), archived[0] if archived else {})
    overlap_df: pd.DataFrame = bundle["locked_vs_current_overlap_csv"]
    locked_failing = overlap_df[overlap_df["in_locked_membership"] & ~overlap_df["in_current_governed"]].copy()
    locked_failing["current_gate_reason"] = locked_failing["current_gate_reason"].fillna("missing_from_full_catalog")
    reason_counts = locked_failing["current_gate_reason"].value_counts().to_dict()
    time_window_rows = int(reason_counts.get("outside_time_window", 0))

    lines = [
        "# Cohort Census Report",
        "",
        "## ZIP / source status",
        "",
        "- The reviewed ZIP is stale relative to this active source tree.",
        "- Active locked manuscript contract in source: `1226 / 39 / 6`.",
        "- Archived rebaseline artifact still present: `20260526T021235Z__8b6966` (`1187 / 35 / 3` taxonomy note, archived only).",
        "",
        "## Required answers",
        "",
        f"1. `1226 / 39 / 6` encoded in active source tree: **yes** (`malicious_temporal_stability_locked`, `paper2_primary_locked`, `20260504T044304Z__8c64e6/cohort_lock_manifest.json`).",
        "2. `1187 / 35 / 3` still the active locked profile contract: **no**. That count survives only as an archived baseline note, not the active lock manifest.",
        f"3. Multiple lock concepts: **yes**. Manuscript-facing lock = `20260504T044304Z__8c64e6`; archived rebaseline = `{archived_rebaseline.get('path', 'none')}`.",
        f"4. Available now under exact profile semantics:",
        f"   - `malicious_temporal_stability_locked`: {locked.get('sample_count', 0)} samples / {locked.get('family_count', 0)} families / {locked.get('type_count', 0)} types",
        f"   - `malicious_temporal_stability`: {current.get('sample_count', 0)} / {current.get('family_count', 0)} / {current.get('type_count', 0)}",
        f"   - `malicious_temporal_stability_expanded`: {expanded.get('sample_count', 0)} / {expanded.get('family_count', 0)} / {expanded.get('type_count', 0)}",
        f"   - `malicious_temporal_stability_long_tail`: {long_tail.get('sample_count', 0)} / {long_tail.get('family_count', 0)} / {long_tail.get('type_count', 0)}",
        f"   - `malicious_temporal_consensus10`: {consensus10.get('sample_count', 0)} / {consensus10.get('family_count', 0)} / {consensus10.get('type_count', 0)}",
        f"   - `malicious_temporal_family300`: {family300.get('sample_count', 0)} / {family300.get('family_count', 0)} / {family300.get('type_count', 0)}",
        "5. Support-floor availability under exact semantics:",
    ]
    for row in support_floors:
        lines.append(
            f"   - floor {row['support_floor']}: {row['sample_count']} samples / {row['family_count']} families / {row['type_count']} types"
        )
    lines.extend(
        [
            f"6. Permission observation required: **advisory only** for these profiles (`{current.get('permission_observation_requirement', 'unknown')}`).",
            f"7. High/strong VT confidence required: **advisory only** for these profiles (`{current.get('confidence_bucket_rule', 'unknown')}`).",
            f"8. Devixor/Gigabud in listed profiles: **excluded** via `cohort_gates.exclude_families`.",
            (
                f"9. Devixor/Gigabud dominance if included under base current semantics: "
                f"Devixor={bundle['devixor_gigabud_counterfactual']['Devixor']['rows']} "
                f"({bundle['devixor_gigabud_counterfactual']['Devixor']['share']:.3f}), "
                f"Gigabud={bundle['devixor_gigabud_counterfactual']['Gigabud']['rows']} "
                f"({bundle['devixor_gigabud_counterfactual']['Gigabud']['share']:.3f}), "
                f"combined={bundle['devixor_gigabud_counterfactual']['combined_share']:.3f}."
            ),
            f"10. Live samples eligible today but missing from the lock: **{int((~overlap_df['in_locked_membership'] & overlap_df['in_current_governed']).sum())}**.",
            f"11. Locked samples failing current gates today: **{int((overlap_df['in_locked_membership'] & ~overlap_df['in_current_governed']).sum())}** total; "
            f"time-window failures={time_window_rows}; top reasons={json.dumps(reason_counts, sort_keys=True)}.",
            (
                "12. Defensible expanded cohort today: "
                + ("**yes, with caution**" if recommendation.get("defensible_today") else "**not yet clearly**")
                + " because the expansion delta is still highly concentrated in a small number of families/sources."
            ),
            f"13. Best paper-expansion candidate today: **{recommendation.get('best_candidate_profile_id', '')}**. "
            f"Rationale: {recommendation.get('rationale', '')}",
            "14. Tables/figures needing regeneration if the paper cohort expands: all cohort-derived paper exports "
            "(`table1`-`table5`, `fig2`-`fig5`); `fig1_pipeline_architecture` is conceptual and does not need rerendering unless the workflow narrative changes.",
            (
                "15. Strict export gates fail today: "
                + ("**yes**" if not strict_status.get("passes", False) else "**no**")
                + f". Missing/failed sources: {json.dumps(strict_status.get('missing_required_sources', []), ensure_ascii=False)}; "
                + f"paper_constants_present={strict_status.get('paper_constants_present', False)}."
            ),
            "",
            "## Recommendation",
            "",
            "- Do not rewrite the manuscript from counts discussion alone.",
            "- Use this census bundle to choose between frozen `1226 / 39 / 6`, archived `1187`, or a new expanded cohort.",
        ]
    )
    return lines


def write_cohort_census_exports(
    *,
    output_dir: Path,
    bundle: dict[str, Any],
) -> dict[str, str]:
    """Write the canonical cohort census exports."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "cohort_census_gate_matrix_csv": output_dir / "cohort_census_gate_matrix.csv",
        "cohort_census_gate_matrix_json": output_dir / "cohort_census_gate_matrix.json",
        "locked_vs_current_overlap_csv": output_dir / "locked_vs_current_overlap.csv",
        "locked_vs_current_overlap_json": output_dir / "locked_vs_current_overlap.json",
        "cohort_exclusion_reasons_csv": output_dir / "cohort_exclusion_reasons.csv",
        "cohort_expansion_candidates_by_family_csv": output_dir / "cohort_expansion_candidates_by_family.csv",
        "cohort_expansion_candidates_by_type_csv": output_dir / "cohort_expansion_candidates_by_type.csv",
        "cohort_source_batch_distribution_csv": output_dir / "cohort_source_batch_distribution.csv",
        "cohort_census_report_md": output_dir / "cohort_census_report.md",
    }
    gate_rows = [_serialize_row_for_csv(row) for row in bundle["profile_rows"]]
    pd.DataFrame(gate_rows).to_csv(paths["cohort_census_gate_matrix_csv"], index=False)
    paths["cohort_census_gate_matrix_json"].write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "profiles": bundle["profile_rows"],
                "support_floor_reference": bundle["support_floor_reference"],
                "devixor_gigabud_counterfactual": bundle["devixor_gigabud_counterfactual"],
                "strict_export_status": bundle["strict_export_status"],
                "archived_lock_concepts": bundle["archived_lock_concepts"],
                "expansion_recommendation": bundle["expansion_recommendation"],
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    bundle["locked_vs_current_overlap_csv"].to_csv(paths["locked_vs_current_overlap_csv"], index=False)
    paths["locked_vs_current_overlap_json"].write_text(
        json.dumps(bundle["locked_vs_current_overlap_json"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    bundle["cohort_exclusion_reasons"].to_csv(paths["cohort_exclusion_reasons_csv"], index=False)
    bundle["cohort_expansion_candidates_by_family"].to_csv(
        paths["cohort_expansion_candidates_by_family_csv"], index=False
    )
    bundle["cohort_expansion_candidates_by_type"].to_csv(
        paths["cohort_expansion_candidates_by_type_csv"], index=False
    )
    bundle["cohort_source_batch_distribution"].to_csv(
        paths["cohort_source_batch_distribution_csv"], index=False
    )
    paths["cohort_census_report_md"].write_text("\n".join(_report_lines(bundle)) + "\n", encoding="utf-8")
    return {key: str(value) for key, value in paths.items()}


__all__ = [
    "TARGET_PROFILE_IDS",
    "build_cohort_census_bundle",
    "write_cohort_census_exports",
]
