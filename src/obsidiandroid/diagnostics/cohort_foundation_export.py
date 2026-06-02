"""Emit cohort foundation artifacts for self-service DB / profile reconciliation.

Artifacts under ``diagnostics/`` summarize **SQL profile scope** (database head counts from
``get_type_cohort_gate_stats``) versus the **prepared cohort** (the returned ``samples_df``).
See ``obsidiandroid.diagnostics.cohort_vocabulary`` for canonical manifest key names.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.database import db_config

from .cohort_vocabulary import KEY_COHORT_PREPARED_ROW_COUNT, KEY_COHORT_SQL_SCOPE_ROW_COUNT


COHORT_SOURCE_TABLES = (
    "malware_sample_catalog",
    "malware_artifact_hash_registry (ranked subquery)",
    "virustotal_sample_scan_summary (ranked subquery)",
    "v_android_apk_family_resolved (ranked subquery)",
    "android_malware_family",
    "android_malware_type",
)


def _pct(numer: int, denom: int) -> float:
    if denom <= 0:
        return 0.0
    return round(100.0 * float(numer) / float(denom), 4)


def _family_shares(samples_df: pd.DataFrame, *, col: str = "family_canonical") -> dict[str, Any]:
    if col not in samples_df.columns or samples_df.empty:
        return {
            "family_count": 0,
            "type_count": 0,
            "top_family": "",
            "top_family_count": 0,
            "top_family_share_pct": 0.0,
            "top3_share_pct": 0.0,
            "top5_share_pct": 0.0,
            "family_distribution": {},
            "type_distribution": {},
        }
    total = int(len(samples_df))
    fc = samples_df[col].fillna("unknown").astype(str)
    vc = fc.value_counts()
    top = str(vc.index[0]) if len(vc) else ""
    top_n = int(vc.iloc[0]) if len(vc) else 0
    top3 = int(vc.head(3).sum()) if len(vc) else 0
    top5 = int(vc.head(5).sum()) if len(vc) else 0
    type_dist: dict[str, int] = {}
    if "type_slug" in samples_df.columns:
        type_dist = (
            samples_df["type_slug"].fillna("unknown").astype(str).value_counts().head(40).to_dict()
        )
    fam_dist = {str(k): int(v) for k, v in vc.head(50).items()}
    type_count = int(samples_df["type_slug"].nunique()) if "type_slug" in samples_df.columns else 0
    return {
        "family_count": int(vc.shape[0]),
        "type_count": type_count,
        "top_family": top,
        "top_family_count": top_n,
        "top_family_share_pct": _pct(top_n, total),
        "top3_share_pct": _pct(top3, total),
        "top5_share_pct": _pct(top5, total),
        "family_distribution": fam_dist,
        "type_distribution": {str(k): int(v) for k, v in type_dist.items()},
    }


def _low_support_families_retained(
    samples_df: pd.DataFrame,
    *,
    min_support_configured: int,
    family_col: str = "family_canonical",
) -> list[dict[str, Any]]:
    if family_col not in samples_df.columns or samples_df.empty:
        return []
    counts = samples_df.groupby(family_col, dropna=False).size()
    out: list[dict[str, Any]] = []
    for fam, cnt in counts.items():
        c = int(cnt)
        if c < int(min_support_configured):
            out.append({"family": str(fam), "rows_in_cohort": c, "below_threshold": int(min_support_configured)})
    out.sort(key=lambda x: x["rows_in_cohort"])
    return out


def _top_distribution(
    samples_df: pd.DataFrame,
    column: str,
    *,
    top_n: int = 20,
) -> dict[str, int]:
    if column not in samples_df.columns or samples_df.empty:
        return {}
    series = samples_df[column].fillna("").astype(str).str.strip()
    series = series[series != ""]
    if series.empty:
        return {}
    return {str(k): int(v) for k, v in series.value_counts().head(top_n).items()}


def _normalize_text_series(samples_df: pd.DataFrame, column: str) -> pd.Series:
    if samples_df.empty:
        return pd.Series([], dtype="object")
    if column not in samples_df.columns:
        return pd.Series([""] * len(samples_df), index=samples_df.index, dtype="object")
    return samples_df[column].fillna("").astype(str).str.strip()


def _top_android_drift_groups(
    samples_df: pd.DataFrame,
    *,
    group_columns: tuple[str, ...],
    top_n: int = 10,
) -> list[dict[str, Any]]:
    if samples_df.empty or not all(col in samples_df.columns for col in group_columns):
        return []

    frame = samples_df.copy()
    for col in group_columns:
        frame[col] = _normalize_text_series(frame, col)
        frame[col] = frame[col].replace("", "<blank>")

    lane = _normalize_text_series(frame, "analysis_lane").str.lower()
    target = _normalize_text_series(frame, "payload_target_platform").str.lower()
    label_kind = _normalize_text_series(frame, "sample_label_kind").str.lower()
    vt_token = _normalize_text_series(frame, "vt_family_token")
    family_raw = _normalize_text_series(frame, "family_label_raw").str.lower()
    family_canonical = _normalize_text_series(frame, "family_canonical").str.lower()

    frame["issue_non_android_lane"] = lane != "android_artifact"
    frame["issue_non_android_target"] = (target != "") & (target != "android")
    frame["issue_weak_label"] = label_kind.isin(
        {"filename", "hash_like", "opaque_string", "unclassified"}
    ) & ~family_canonical.isin({"", "unknown", "other", "unmapped", "none", "null"})
    frame["issue_blank_family_with_token"] = (
        (vt_token != "")
        & family_raw.isin({"", "unknown", "generic", "unclassified", "unlabeled"})
    )
    frame["issue_family_conflict"] = (
        ~family_raw.isin({"", "unknown", "generic", "unclassified", "unlabeled"})
        & ~family_canonical.isin({"", "unknown", "other", "unmapped", "none", "null"})
        & (family_raw != family_canonical)
    )
    issue_columns = [
        "issue_non_android_lane",
        "issue_non_android_target",
        "issue_weak_label",
        "issue_blank_family_with_token",
        "issue_family_conflict",
    ]
    frame["issue_rows"] = frame[issue_columns].any(axis=1)
    frame = frame[frame["issue_rows"]].copy()
    if frame.empty:
        return []

    grouped = (
        frame.groupby(list(group_columns), dropna=False)
        .agg(
            rows=("issue_rows", "size"),
            non_android_lane_rows=("issue_non_android_lane", "sum"),
            non_android_payload_target_rows=("issue_non_android_target", "sum"),
            weak_label_rows=("issue_weak_label", "sum"),
            blank_family_raw_with_vt_token_rows=("issue_blank_family_with_token", "sum"),
            raw_family_vs_canonical_conflict_rows=("issue_family_conflict", "sum"),
        )
        .reset_index()
    )
    grouped["issue_events"] = (
        grouped["non_android_lane_rows"]
        + grouped["non_android_payload_target_rows"]
        + grouped["weak_label_rows"]
        + grouped["blank_family_raw_with_vt_token_rows"]
        + grouped["raw_family_vs_canonical_conflict_rows"]
    )
    grouped = grouped.sort_values(
        by=["issue_events", "rows"],
        ascending=[False, False],
        kind="stable",
    ).head(top_n)
    return grouped.to_dict(orient="records")


def _catalog_semantics_summary(samples_df: pd.DataFrame) -> dict[str, Any]:
    summary = {
        "analysis_lane_distribution": _top_distribution(samples_df, "analysis_lane"),
        "sample_label_kind_distribution": _top_distribution(samples_df, "sample_label_kind"),
        "payload_target_platform_distribution": _top_distribution(samples_df, "payload_target_platform"),
        "payload_target_source_distribution": _top_distribution(samples_df, "payload_target_source"),
        "unknown_artifact_kind_distribution": _top_distribution(samples_df, "unknown_artifact_kind"),
        "source_batch_label_distribution": _top_distribution(samples_df, "source_batch_label"),
        "top_drift_families": _top_android_drift_groups(
            samples_df,
            group_columns=("family_canonical",),
        ),
        "top_drift_types": _top_android_drift_groups(
            samples_df,
            group_columns=("type_slug",),
        ),
        "top_drift_source_batches": _top_android_drift_groups(
            samples_df,
            group_columns=("source_batch_label",),
        ),
    }
    if "analysis_lane" in samples_df.columns and not samples_df.empty:
        lane = samples_df["analysis_lane"].fillna("").astype(str).str.strip().str.lower()
        summary["non_android_lane_rows"] = int((lane != "android_artifact").sum())
    else:
        summary["non_android_lane_rows"] = 0
    if "payload_target_platform" in samples_df.columns and not samples_df.empty:
        target = (
            samples_df["payload_target_platform"].fillna("").astype(str).str.strip().str.lower()
        )
        summary["non_android_payload_target_rows"] = int(
            ((target != "") & (target != "android")).sum()
        )
    else:
        summary["non_android_payload_target_rows"] = 0
    if "sample_label_kind" in samples_df.columns and not samples_df.empty:
        kinds = samples_df["sample_label_kind"].fillna("").astype(str).str.strip().str.lower()
        summary["hash_like_label_rows"] = int((kinds == "hash_like").sum())
        summary["opaque_label_rows"] = int((kinds == "opaque_string").sum())
        summary["unclassified_label_rows"] = int((kinds == "unclassified").sum())
        summary["filename_label_rows"] = int((kinds == "filename").sum())
    else:
        summary["hash_like_label_rows"] = 0
        summary["opaque_label_rows"] = 0
        summary["unclassified_label_rows"] = 0
        summary["filename_label_rows"] = 0
    if "vt_family_token" in samples_df.columns and not samples_df.empty:
        vt_token = samples_df["vt_family_token"].fillna("").astype(str).str.strip()
        summary["vt_family_token_rows"] = int((vt_token != "").sum())
    else:
        summary["vt_family_token_rows"] = 0
    if (
        "vt_family_token" in samples_df.columns
        and "family_label_raw" in samples_df.columns
        and not samples_df.empty
    ):
        vt_token = samples_df["vt_family_token"].fillna("").astype(str).str.strip()
        family_raw = samples_df["family_label_raw"].fillna("").astype(str).str.strip().str.lower()
        summary["blank_family_raw_with_vt_token_rows"] = int(
            (
                (vt_token != "")
                & family_raw.isin({"", "unknown", "generic", "unclassified", "unlabeled"})
            ).sum()
        )
    else:
        summary["blank_family_raw_with_vt_token_rows"] = 0
    if "family_canonical" in samples_df.columns and not samples_df.empty:
        family_canonical = samples_df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
    else:
        family_canonical = pd.Series([], dtype="object")
    if (
        "sample_label_kind" in samples_df.columns
        and "family_canonical" in samples_df.columns
        and not samples_df.empty
    ):
        kinds = samples_df["sample_label_kind"].fillna("").astype(str).str.strip().str.lower()
        summary["weak_label_with_canonical_family_rows"] = int(
            (
                kinds.isin({"filename", "hash_like", "opaque_string", "unclassified"})
                & ~family_canonical.isin({"", "unknown", "other", "unmapped", "none", "null"})
            ).sum()
        )
    else:
        summary["weak_label_with_canonical_family_rows"] = 0
    if (
        "family_label_raw" in samples_df.columns
        and "family_canonical" in samples_df.columns
        and not samples_df.empty
    ):
        family_raw = samples_df["family_label_raw"].fillna("").astype(str).str.strip().str.lower()
        summary["raw_family_vs_canonical_conflict_rows"] = int(
            (
                ~family_raw.isin({"", "unknown", "generic", "unclassified", "unlabeled"})
                & ~family_canonical.isin({"", "unknown", "other", "unmapped", "none", "null"})
                & (family_raw != family_canonical)
            ).sum()
        )
    else:
        summary["raw_family_vs_canonical_conflict_rows"] = 0
    return summary


def build_catalog_semantics_summary(
    samples_df: pd.DataFrame,
    *,
    scope: str = "sql_governed_android_cohort",
) -> dict[str, Any]:
    """Return normalized catalog-semantics summary for an already loaded cohort frame.

    This mirrors the shape previously produced by the SQL-scope semantics profiler so callers
    that already materialized the governed cohort do not need to pay for a second full DB scan.
    """
    summary = _catalog_semantics_summary(samples_df)
    return {
        "scope": str(scope or "sql_governed_android_cohort"),
        **summary,
    }


def _catalog_semantics_delta(
    prepared: dict[str, Any],
    sql_scope: dict[str, Any],
) -> dict[str, int]:
    """Summarize how much Python-side preparation reduced visible cohort drift."""
    metrics = (
        "non_android_lane_rows",
        "non_android_payload_target_rows",
        "filename_label_rows",
        "hash_like_label_rows",
        "opaque_label_rows",
        "unclassified_label_rows",
        "blank_family_raw_with_vt_token_rows",
        "weak_label_with_canonical_family_rows",
        "raw_family_vs_canonical_conflict_rows",
    )
    out: dict[str, int] = {}
    for metric in metrics:
        prepared_value = int(prepared.get(metric, 0) or 0)
        sql_scope_value = int(sql_scope.get(metric, 0) or 0)
        out[metric] = sql_scope_value - prepared_value
    return out


def _missing_vt_time_rate(samples_df: pd.DataFrame) -> float:
    sub = "vt_first_submission_date" if "vt_first_submission_date" in samples_df.columns else None
    itw = "vt_first_seen_itw_date" if "vt_first_seen_itw_date" in samples_df.columns else None
    eff = "effective_first_seen_at_utc" if "effective_first_seen_at_utc" in samples_df.columns else None
    if eff and eff in samples_df.columns:
        m = samples_df[eff].isna().sum()
        return _pct(int(m), len(samples_df))
    if sub and itw:
        m = (samples_df[sub].isna() & samples_df[itw].isna()).sum()
        return _pct(int(m), len(samples_df))
    if sub:
        m = samples_df[sub].isna().sum()
        return _pct(int(m), len(samples_df))
    return 0.0


def build_cohort_foundation_payload(
    *,
    run_id: str,
    profile_id: str,
    profile: dict[str, Any],
    gate_stats: dict[str, Any],
    samples_df: pd.DataFrame,
    time_contract: dict[str, Any],
    type_slug: str | None,
    min_samples_per_family_sql: int | None,
    configured_min_samples_per_family: int | None,
    diagnostic_min_samples_per_family: int,
    support_floor_mode: str,
) -> dict[str, Any]:
    """Assemble JSON-serializable cohort foundation summary."""
    gates = profile.get("cohort_gates", {}) if isinstance(profile, dict) else {}
    n = int(len(samples_df))
    sid_u = int(samples_df["sample_id"].nunique()) if "sample_id" in samples_df.columns else 0
    dup_surplus = max(0, n - sid_u)
    sha_u = int(samples_df["sha256"].nunique()) if "sha256" in samples_df.columns else 0
    pkg_missing = 0
    if "android_package_name" in samples_df.columns:
        pkg_missing = int(
            (samples_df["android_package_name"].fillna("").astype(str).str.strip() == "").sum()
        )
    shares = _family_shares(samples_df)
    low_sup = _low_support_families_retained(
        samples_df,
        min_support_configured=max(1, int(diagnostic_min_samples_per_family)),
    )
    upstream_min = gates.get("upstream_expected_min_gate_total")
    env_min = os.environ.get("SCYTALEDROID_COHORT_EXPECTED_MIN_GATE_TOTAL", "").strip()
    upstream_min_i: int | None = None
    for candidate in (upstream_min, env_min or None):
        if candidate is None or str(candidate).strip() == "":
            continue
        try:
            upstream_min_i = int(candidate)
            break
        except (TypeError, ValueError):
            continue
    sql_scope_total = int(gate_stats.get("total_candidates", 0) or 0)
    governed_sql_total = int(
        gate_stats.get("governed_cohort_count", gate_stats.get("final_count_estimate", 0)) or 0
    )
    interim_notes: list[str] = []
    if upstream_min_i is not None and sql_scope_total < upstream_min_i:
        interim_notes.append(
            f"Cohort SQL scope row count ({sql_scope_total}) is below expected minimum ({upstream_min_i}); "
            "the database snapshot may be incomplete or profile gates may exclude a large share — "
            "not a final paper cohort."
        )
        interim_notes.append(
            "Current DB snapshot may be incomplete due to upstream Erebus reprocessing. "
            "Treat this run as pipeline validation, not final paper evidence."
        )

    payload: dict[str, Any] = {
        "schema_version": "1.0",
        KEY_COHORT_SQL_SCOPE_ROW_COUNT: sql_scope_total,
        KEY_COHORT_PREPARED_ROW_COUNT: n,
        "run_id": run_id,
        "profile_id": profile_id,
        "primary_db_name": getattr(db_config, "DB_NAME", ""),
        "permission_intel_db_name": getattr(db_config, "PERMISSION_INTEL_DB_NAME", ""),
        "cohort_source_tables": list(COHORT_SOURCE_TABLES),
        "time_contract": {
            "enabled": time_contract.get("enabled"),
            "start_utc": time_contract.get("start_utc"),
            "end_utc": time_contract.get("end_utc"),
            "timestamp_field": time_contract.get("timestamp_field"),
            "require_effective_first_seen": time_contract.get("require_effective_first_seen"),
        },
        "type_slug_filter_effective": type_slug,
        "support_floor_mode": str(support_floor_mode or ""),
        "min_samples_per_family_configured": (
            int(configured_min_samples_per_family)
            if configured_min_samples_per_family not in (None, "")
            else None
        ),
        "diagnostic_min_samples_per_family": int(diagnostic_min_samples_per_family),
        "min_samples_per_family_applied_in_sql": min_samples_per_family_sql is not None,
        "min_samples_per_family_sql_value": min_samples_per_family_sql,
        "exclude_families_deferred_by_snapshot_lock": bool(
            getattr(samples_df, "attrs", {}).get("exclude_families_deferred_by_snapshot_lock", False)
        ),
        "requested_excluded_families": list(
            getattr(samples_df, "attrs", {}).get("requested_exclude_families", ()) or ()
        ),
        "gate_stats": {
            "total_candidates": int(gate_stats.get("total_candidates", 0) or 0),
            "excluded_unmapped_family": int(gate_stats.get("excluded_unmapped_family", 0) or 0),
            "excluded_unknown_type_slug": int(gate_stats.get("excluded_unknown_type_slug", 0) or 0),
            "excluded_missing_sha256": int(gate_stats.get("excluded_missing_sha256", 0) or 0),
            "excluded_missing_hash_registry": int(gate_stats.get("excluded_missing_hash_registry", 0) or 0),
            "excluded_missing_package_name": int(gate_stats.get("excluded_missing_package_name", 0) or 0),
            "excluded_low_support": int(gate_stats.get("excluded_low_support", 0) or 0),
            "excluded_weak_label_kind": int(gate_stats.get("excluded_weak_label_kind", 0) or 0),
            "excluded_family_label_conflict": int(gate_stats.get("excluded_family_label_conflict", 0) or 0),
            "governed_cohort_count_sql": governed_sql_total,
            "final_count_estimate_sequential_legacy": gate_stats.get("final_count_estimate_sequential_legacy"),
        },
        "cohort_attrition": {
            "sql_scope_total": sql_scope_total,
            "governed_sql_total": governed_sql_total,
            "prepared_total": n,
            "sql_scope_to_governed_pct": _pct(governed_sql_total, sql_scope_total),
            "sql_scope_to_prepared_pct": _pct(n, sql_scope_total),
            "governed_to_prepared_pct": _pct(n, governed_sql_total),
        },
        "profile_excluded_family_canonical": list(gate_stats.get("excluded_family_canonical") or []),
        "loaded_dataframe": {
            "rows": n,
            "columns": int(samples_df.shape[1]),
            "distinct_sample_id": sid_u,
            "distinct_sha256": sha_u,
            "duplicate_sample_id_surplus": dup_surplus,
        },
        "missing_package_rate_pct": _pct(pkg_missing, n),
        "missing_vt_timestamp_rate_pct": _missing_vt_time_rate(samples_df),
        "family_type_summary": shares,
        "catalog_semantics_summary": _catalog_semantics_summary(samples_df),
        "catalog_semantics_sql_scope": (
            dict(samples_df.attrs.get("catalog_semantics_sql_scope", {}))
            if hasattr(samples_df, "attrs") and isinstance(samples_df.attrs.get("catalog_semantics_sql_scope"), dict)
            else {}
        ),
        "catalog_semantics_delta": {},
        "low_support_families_retained_in_cohort": low_sup[:200],
        "cohort_definition_notes": [
            "Prepared cohort: rows in samples_df after cohort SQL fetch plus in-Python dataset/time contract filters.",
            "gate_stats.total_candidates: SQL head count for the same profile scope (joins + time window + exclusions).",
            "Marginal exclusion buckets in gate_stats can overlap; trust governed_cohort_count_sql and loaded_dataframe.rows.",
            "min_samples_per_family applies in SQL only when explicitly configured for membership gating.",
            "Diagnostic support floors (20/10/5/3/1) do not imply sample admission gates.",
            "Catalog semantics fields are additive Erebus diagnostics only; they do not redefine Android cohort membership or type authority inside ObsidianDroid.",
            "Final research totals may change until upstream Erebus ingestion finishes rebuilding.",
        ],
        "interim_rebuild_warnings": interim_notes,
    }
    payload["catalog_semantics_delta"] = _catalog_semantics_delta(
        payload.get("catalog_semantics_summary", {}),
        payload.get("catalog_semantics_sql_scope", {}),
    )
    return payload


def export_cohort_foundation_bundle(
    *,
    diagnostics_dir: Path,
    run_id: str,
    profile_id: str,
    profile: dict[str, Any],
    gate_stats: dict[str, Any],
    samples_df: pd.DataFrame,
    time_contract: dict[str, Any],
    type_slug: str | None,
    min_samples_per_family_sql: int | None,
    configured_min_samples_per_family: int | None,
    diagnostic_min_samples_per_family: int,
    support_floor_mode: str,
    artifact_list: list[str] | None = None,
) -> list[str]:
    """Write cohort_foundation.{json,md,csv} under diagnostics_dir. Returns written paths."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    payload = build_cohort_foundation_payload(
        run_id=run_id,
        profile_id=profile_id,
        profile=profile,
        gate_stats=gate_stats,
        samples_df=samples_df,
        time_contract=time_contract,
        type_slug=type_slug,
        min_samples_per_family_sql=min_samples_per_family_sql,
        configured_min_samples_per_family=configured_min_samples_per_family,
        diagnostic_min_samples_per_family=diagnostic_min_samples_per_family,
        support_floor_mode=support_floor_mode,
    )
    paths: list[str] = []

    json_path = diagnostics_dir / "cohort_foundation.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    paths.append(str(json_path))

    counts_rows: list[dict[str, str]] = []
    for key, val in payload.get("gate_stats", {}).items():
        counts_rows.append({"metric": key, "value": str(val), "section": "cohort_sql_scope"})
    ld = payload.get("loaded_dataframe", {})
    for key, val in ld.items():
        counts_rows.append({"metric": f"loaded_{key}", "value": str(val), "section": "prepared_cohort"})
    counts_rows.append(
        {"metric": "missing_package_rate_pct", "value": str(payload.get("missing_package_rate_pct")), "section": "quality"}
    )
    counts_rows.append(
        {
            "metric": "missing_vt_timestamp_rate_pct",
            "value": str(payload.get("missing_vt_timestamp_rate_pct")),
            "section": "quality",
        }
    )
    ft = payload.get("family_type_summary", {})
    counts_rows.append({"metric": "family_count", "value": str(ft.get("family_count")), "section": "families"})
    counts_rows.append({"metric": "type_count", "value": str(ft.get("type_count")), "section": "families"})
    counts_rows.append({"metric": "top_family_share_pct", "value": str(ft.get("top_family_share_pct")), "section": "families"})
    attrition = payload.get("cohort_attrition", {})
    for key in (
        "sql_scope_total",
        "governed_sql_total",
        "prepared_total",
        "sql_scope_to_governed_pct",
        "sql_scope_to_prepared_pct",
        "governed_to_prepared_pct",
    ):
        counts_rows.append({"metric": key, "value": str(attrition.get(key, 0)), "section": "cohort_attrition"})
    semantics = payload.get("catalog_semantics_summary", {})
    semantics_sql_scope = payload.get("catalog_semantics_sql_scope", {})
    semantics_delta = payload.get("catalog_semantics_delta", {})
    for key in (
        "non_android_lane_rows",
        "non_android_payload_target_rows",
        "hash_like_label_rows",
        "opaque_label_rows",
        "unclassified_label_rows",
        "filename_label_rows",
        "vt_family_token_rows",
        "blank_family_raw_with_vt_token_rows",
        "weak_label_with_canonical_family_rows",
        "raw_family_vs_canonical_conflict_rows",
    ):
        counts_rows.append({"metric": key, "value": str(semantics.get(key, 0)), "section": "catalog_semantics"})
        counts_rows.append(
            {
                "metric": key,
                "value": str(semantics_sql_scope.get(key, 0)),
                "section": "catalog_semantics_sql_scope",
            }
        )
        counts_rows.append(
            {
                "metric": key,
                "value": str(semantics_delta.get(key, 0)),
                "section": "catalog_semantics_delta",
            }
        )

    if bool(getattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True)):
        counts_path = diagnostics_dir / "cohort_foundation_counts.csv"
        counts_path.parent.mkdir(parents=True, exist_ok=True)
        with counts_path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["section", "metric", "value"])
            w.writeheader()
            w.writerows(counts_rows)
        paths.append(str(counts_path))

    schema_rows: list[dict[str, Any]] = []
    for col in samples_df.columns:
        ser = samples_df[col]
        schema_rows.append(
            {
                "column": col,
                "dtype": str(ser.dtype),
                "non_null_count": int(ser.notna().sum()),
                "null_count": int(ser.isna().sum()),
                "nunique": int(ser.nunique(dropna=True)),
            }
        )
    if bool(getattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True)):
        schema_path = diagnostics_dir / "cohort_foundation_schema.csv"
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        with schema_path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(
                fh,
                fieldnames=["column", "dtype", "non_null_count", "null_count", "nunique"],
            )
            w.writeheader()
            w.writerows(schema_rows)
        paths.append(str(schema_path))

    md_lines = [
        "# Cohort foundation (samples stage)",
        "",
        f"- **run_id:** `{run_id}`",
        f"- **profile_id:** `{profile_id}`",
        f"- **primary DB:** `{payload.get('primary_db_name')}`",
        "",
        "## Time contract",
        "",
        f"- start: `{payload.get('time_contract', {}).get('start_utc')}`",
        f"- end: `{payload.get('time_contract', {}).get('end_utc')}`",
        "",
        "## Cohort policy contract",
        "",
        f"- min_samples_per_family configured: `{payload.get('min_samples_per_family_configured')}`",
        f"- min_samples_per_family applied in SQL: `{payload.get('min_samples_per_family_applied_in_sql')}`",
        f"- min_samples_per_family SQL value: `{payload.get('min_samples_per_family_sql_value')}`",
        f"- exclude_families_deferred_by_snapshot_lock: `{payload.get('exclude_families_deferred_by_snapshot_lock')}`",
        f"- requested_excluded_families: `{', '.join(payload.get('requested_excluded_families') or []) or '(none)'}`",
        "",
        "## Database: cohort SQL scope (``gate_stats``)",
        "",
        f"- SQL profile scope (``total_candidates``): **{payload['gate_stats']['total_candidates']}**",
        f"- SQL governed row count (``governed_cohort_count_sql``): **{payload['gate_stats']['governed_cohort_count_sql']}**",
        f"- excluded_unmapped_family: {payload['gate_stats']['excluded_unmapped_family']}",
        f"- excluded_unknown_type_slug: {payload['gate_stats']['excluded_unknown_type_slug']}",
        f"- excluded_missing_sha256 / hash_registry: {payload['gate_stats']['excluded_missing_sha256']} / "
        f"{payload['gate_stats']['excluded_missing_hash_registry']}",
        "",
        "## Prepared cohort: loaded dataframe",
        "",
        f"- rows × columns: **{ld.get('rows')}** × **{ld.get('columns')}**",
        f"- distinct sample_id: {ld.get('distinct_sample_id')} (duplicate surplus {ld.get('duplicate_sample_id_surplus')})",
        f"- distinct sha256: {ld.get('distinct_sha256')}",
        "",
        "## Cohort attrition",
        "",
        f"- SQL scope → governed: {attrition.get('governed_sql_total', 0)}/{attrition.get('sql_scope_total', 0)} ({attrition.get('sql_scope_to_governed_pct', 0)}%)",
        f"- SQL scope → prepared: {attrition.get('prepared_total', 0)}/{attrition.get('sql_scope_total', 0)} ({attrition.get('sql_scope_to_prepared_pct', 0)}%)",
        f"- governed → prepared: {attrition.get('prepared_total', 0)}/{attrition.get('governed_sql_total', 0)} ({attrition.get('governed_to_prepared_pct', 0)}%)",
        "",
        "## Catalog semantics",
        "",
        f"- non_android_lane_rows: {semantics.get('non_android_lane_rows', 0)}",
        f"- non_android_payload_target_rows: {semantics.get('non_android_payload_target_rows', 0)}",
        f"- filename_label_rows: {semantics.get('filename_label_rows', 0)}",
        f"- hash_like_label_rows: {semantics.get('hash_like_label_rows', 0)}",
        f"- opaque_label_rows: {semantics.get('opaque_label_rows', 0)}",
        f"- unclassified_label_rows: {semantics.get('unclassified_label_rows', 0)}",
        f"- vt_family_token_rows: {semantics.get('vt_family_token_rows', 0)}",
        f"- blank_family_raw_with_vt_token_rows: {semantics.get('blank_family_raw_with_vt_token_rows', 0)}",
        f"- weak_label_with_canonical_family_rows: {semantics.get('weak_label_with_canonical_family_rows', 0)}",
        f"- raw_family_vs_canonical_conflict_rows: {semantics.get('raw_family_vs_canonical_conflict_rows', 0)}",
        "",
        "## What this cohort is / is not",
        "",
        *(f"- {note}" for note in payload.get("cohort_definition_notes", [])),
        "",
    ]
    lane_dist = semantics.get("analysis_lane_distribution") or {}
    if lane_dist:
        md_lines.extend(["### Top analysis lanes", ""])
        for key, value in lane_dist.items():
            md_lines.append(f"- `{key}`: {value}")
        md_lines.append("")
    label_dist = semantics.get("sample_label_kind_distribution") or {}
    if label_dist:
        md_lines.extend(["### Top sample-label kinds", ""])
        for key, value in label_dist.items():
            md_lines.append(f"- `{key}`: {value}")
        md_lines.append("")
    target_dist = semantics.get("payload_target_platform_distribution") or {}
    if target_dist:
        md_lines.extend(["### Top payload targets", ""])
        for key, value in target_dist.items():
            md_lines.append(f"- `{key}`: {value}")
        md_lines.append("")
    batch_dist = semantics.get("source_batch_label_distribution") or {}
    if batch_dist:
        md_lines.extend(["### Top source batches", ""])
        for key, value in batch_dist.items():
            md_lines.append(f"- `{key}`: {value}")
        md_lines.append("")
    if semantics_sql_scope:
        md_lines.extend(["## Catalog semantics (SQL scope preview)", ""])
        md_lines.append(
            f"- non_android_lane_rows: {semantics_sql_scope.get('non_android_lane_rows', 0)}"
        )
        md_lines.append(
            f"- non_android_payload_target_rows: {semantics_sql_scope.get('non_android_payload_target_rows', 0)}"
        )
        md_lines.append(
            f"- weak_label_with_canonical_family_rows: {semantics_sql_scope.get('weak_label_with_canonical_family_rows', 0)}"
        )
        md_lines.append(
            f"- raw_family_vs_canonical_conflict_rows: {semantics_sql_scope.get('raw_family_vs_canonical_conflict_rows', 0)}"
        )
        md_lines.append("")
    if semantics_delta:
        md_lines.extend(["## Catalog semantics delta (SQL scope minus prepared cohort)", ""])
        for key in (
            "non_android_lane_rows",
            "non_android_payload_target_rows",
            "filename_label_rows",
            "hash_like_label_rows",
            "opaque_label_rows",
            "unclassified_label_rows",
            "blank_family_raw_with_vt_token_rows",
            "weak_label_with_canonical_family_rows",
            "raw_family_vs_canonical_conflict_rows",
        ):
            md_lines.append(f"- {key}: {semantics_delta.get(key, 0)}")
        md_lines.append("")
    for heading, rows, key_name in (
        ("### Top drift families", semantics.get("top_drift_families") or [], "family_canonical"),
        ("### Top drift types", semantics.get("top_drift_types") or [], "type_slug"),
        (
            "### Top drift source batches",
            semantics.get("top_drift_source_batches") or [],
            "source_batch_label",
        ),
    ):
        if not rows:
            continue
        md_lines.extend([heading, ""])
        for row in rows:
            label = str(row.get(key_name, "<blank>") or "<blank>")
            md_lines.append(
                f"- `{label}`: rows={int(row.get('rows', 0))}, "
                f"issue_events={int(row.get('issue_events', 0))}, "
                f"weak_label_rows={int(row.get('weak_label_rows', 0))}, "
                f"family_conflicts={int(row.get('raw_family_vs_canonical_conflict_rows', 0))}"
            )
        md_lines.append("")
    warns = payload.get("interim_rebuild_warnings") or []
    if warns:
        md_lines.extend(["## Warnings", ""])
        md_lines.extend(f"- **{w}**" for w in warns)
        md_lines.append("")
    md_path = diagnostics_dir / "cohort_foundation.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    paths.append(str(md_path))

    if isinstance(artifact_list, list):
        artifact_list.extend(paths)
    return paths


def append_research_warnings_for_upstream_expectation(
    manifest_context: dict[str, Any],
    *,
    profile_id: str,
    sql_scope_row_count: int,
    gates: dict[str, Any],
) -> None:
    """Append pipeline research warnings when optional upstream min threshold is breached."""
    raw = gates.get("upstream_expected_min_gate_total")
    env_min = os.environ.get("SCYTALEDROID_COHORT_EXPECTED_MIN_GATE_TOTAL", "").strip()
    min_g: int | None = None
    for candidate in (raw, env_min or None):
        if candidate is None or str(candidate).strip() == "":
            continue
        try:
            min_g = int(candidate)
            break
        except (TypeError, ValueError):
            continue
    if min_g is None or sql_scope_row_count >= min_g:
        return
    msg = (
        f"cohort_sql_scope_row_count={sql_scope_row_count} is below expected minimum={min_g} "
        "(cohort_gates.upstream_expected_min_gate_total or SCYTALEDROID_COHORT_EXPECTED_MIN_GATE_TOTAL); "
        "the database snapshot may be incomplete or profile gates exclude a large share — not a final paper cohort."
    )
    rw = manifest_context.setdefault("_research_warning_messages", [])
    if isinstance(rw, list) and msg not in rw:
        rw.append(msg)
    msg2 = (
        "Current DB snapshot may be incomplete due to upstream Erebus reprocessing. "
        "Treat this run as pipeline validation, not final paper evidence."
    )
    if isinstance(rw, list) and msg2 not in rw:
        rw.append(msg2)
