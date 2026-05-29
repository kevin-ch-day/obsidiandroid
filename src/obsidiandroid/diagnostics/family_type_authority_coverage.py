"""Read-only authority coverage diagnostics for Android family/type authority."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.database import authority_contracts
from obsidiandroid.database import db_engine
from obsidiandroid.observability import get_logger, log_event


DEFAULT_MD = Path("output") / "diagnostics" / "family_type_authority_coverage_latest.md"
DEFAULT_MISSING = Path("output") / "diagnostics" / "family_type_authority_missing_candidates_latest.csv"
DEFAULT_UNKNOWN_TYPE = Path("output") / "diagnostics" / "family_type_authority_unknown_type_latest.csv"
DEFAULT_YEAR_TYPE = Path("output") / "diagnostics" / "family_type_authority_year_type_latest.csv"

PRIORITY_FAMILY_CURATION = {
    "blankbot",
    "raton",
    "rafel",
    "malibot",
    "pixbankbot",
    "toxicpanda",
    "bingomod",
    "anatsa",
    "frogblight",
    "herodotus",
    "ynrk",
    "fvncbot",
    "india banker 2026",
}
PRIORITY_UNKNOWN_TYPE = {
    "hiddenad",
    "brata",
    "spyc23",
    "bahamut",
    "gravityrat",
    "medusa",
    "brokewell",
    "ghimob",
    "terracotta",
    "fakecall",
    "antidot",
    "copybara",
    "fatboypanel",
}
GENERIC_OR_COARSE = {
    "unknown",
    "trojan",
    "adware",
    "stalkerware",
    "ransomware",
    "infostealer",
    "banker trojan",
    "fraud financial apps",
    "spyware",
    "hiddenadware",
    "masquerading malware",
    "adfraud",
    "dropper",
    "stealer",
    "banker",
    "malware",
    "agent",
}

AUTHORITY_VIEW_SELECT = """
SELECT
    msc.sample_id,
    msc.sha256,
    msc.platform,
    msc.android_package_name,
    msc.vt_first_submission_at_utc,
    fam_norm.family_raw AS family_raw,
    fam_norm.family_lc AS family_lc,
    fam_res.resolved_family_lc,
    msc.classification_primary AS raw_classification_primary,
    msc.classification_subtype AS raw_classification_subtype,
    fam.family_id,
    fam.family_name,
    fam.family_slug,
    typ.type_id,
    typ.type_name,
    typ.type_slug,
    typ.parent_type_id,
    parent_typ.type_slug AS parent_type_slug,
    alias.alias_name AS matched_alias_name,
    CASE
        WHEN alias.alias_id IS NOT NULL THEN 1
        WHEN COALESCE(LOWER(TRIM(fam_norm.family_lc)), '') <> ''
             AND COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') <> ''
             AND LOWER(TRIM(fam_norm.family_lc)) <> LOWER(TRIM(fam_res.resolved_family_lc))
        THEN 1
        ELSE 0
    END AS resolved_via_alias_flag,
    CASE
        WHEN fam.family_id IS NOT NULL
             AND COALESCE(LOWER(TRIM(typ.type_slug)), '') NOT IN ('', 'unknown')
        THEN 'authority_family_typed'
        WHEN fam.family_id IS NOT NULL
             AND COALESCE(LOWER(TRIM(typ.type_slug)), '') IN ('', 'unknown')
        THEN 'authority_family_unknown_type'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = 'unknown'
        THEN 'resolved_unknown'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
        THEN 'missing_resolved_family'
        WHEN LOWER(TRIM(fam_res.resolved_family_lc)) IN (
            'trojan','adware','stalkerware','ransomware','infostealer',
            'banker trojan','fraud financial apps','spyware','hiddenadware',
            'masquerading malware','malware','agent','dropper','stealer',
            'banker','adfraud'
        )
        THEN 'generic_label_candidate'
        ELSE 'resolved_but_no_authority_family'
    END AS authority_bucket,
    CASE
        WHEN fam.family_id IS NOT NULL
             AND COALESCE(LOWER(TRIM(typ.type_slug)), '') NOT IN ('', 'unknown')
        THEN 'authority_family_typed'
        WHEN fam.family_id IS NOT NULL
             AND COALESCE(LOWER(TRIM(typ.type_slug)), '') IN ('', 'unknown')
        THEN 'authority_family_missing_type'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = 'unknown'
        THEN 'resolved_token_unknown'
        WHEN COALESCE(LOWER(TRIM(fam_res.resolved_family_lc)), '') = ''
        THEN 'missing_resolved_family'
        WHEN LOWER(TRIM(fam_res.resolved_family_lc)) IN (
            'trojan','adware','stalkerware','ransomware','infostealer',
            'banker trojan','fraud financial apps','spyware','hiddenadware',
            'masquerading malware','malware','agent','dropper','stealer',
            'banker','adfraud'
        )
        THEN 'resolved_token_coarse_behavior'
        WHEN fam_res.resolved_family_lc REGEXP '[ /\\\\()]'
        THEN 'resolved_token_malformed_or_composite'
        ELSE 'resolved_token_not_in_authority_taxonomy'
    END AS authority_gap_reason,
    CASE
        WHEN fam.family_id IS NULL
             OR COALESCE(LOWER(TRIM(typ.type_slug)), '') IN ('', 'unknown')
        THEN 'authority_unknown'
        WHEN COALESCE(LOWER(TRIM(msc.classification_primary)), '') IN ('', 'unknown', 'null', 'n/a', 'malware')
             AND COALESCE(LOWER(TRIM(msc.classification_subtype)), '') IN ('', 'unknown', 'null', 'n/a')
        THEN 'raw_missing'
        WHEN COALESCE(LOWER(TRIM(msc.classification_subtype)), '') = LOWER(TRIM(typ.type_slug))
        THEN 'raw_subtype_matches_authority'
        WHEN COALESCE(LOWER(TRIM(msc.classification_primary)), '') = LOWER(TRIM(typ.type_slug))
        THEN 'raw_primary_matches_authority'
        WHEN COALESCE(LOWER(TRIM(msc.classification_primary)), '') = 'trojan'
             AND COALESCE(LOWER(TRIM(msc.classification_subtype)), '') IN ('', 'unknown', 'null', 'n/a')
             AND COALESCE(LOWER(TRIM(typ.type_slug)), '') IN ('banker', 'dropper', 'stealer', 'sms-trojan', 'rat', 'spyware', 'adware')
        THEN 'raw_coarse_trojan_matches_parent'
        WHEN COALESCE(LOWER(TRIM(msc.classification_primary)), '') IN ('dropper', 'banker', 'stealer', 'rat', 'spyware', 'adware', 'sms-trojan')
             AND COALESCE(LOWER(TRIM(msc.classification_primary)), '') = LOWER(TRIM(parent_typ.type_slug))
        THEN 'raw_coarse_behavior_matches_parent'
        WHEN COALESCE(LOWER(TRIM(msc.classification_subtype)), '') IN ('dropper', 'banker', 'stealer', 'rat', 'spyware', 'adware', 'sms-trojan')
             AND COALESCE(LOWER(TRIM(msc.classification_subtype)), '') = LOWER(TRIM(parent_typ.type_slug))
        THEN 'raw_coarse_behavior_matches_parent'
        ELSE 'raw_conflicts_with_authority'
    END AS raw_vs_authority_status
FROM malware_sample_catalog AS msc
LEFT JOIN v_android_apk_family_norm AS fam_norm
    ON fam_norm.sample_id = msc.sample_id
LEFT JOIN v_android_apk_family_resolved AS fam_res
    ON fam_res.sample_id = msc.sample_id
LEFT JOIN android_malware_family AS fam
    ON LOWER(TRIM(fam.family_slug)) = LOWER(TRIM(fam_res.resolved_family_lc))
   AND fam.is_active = 1
LEFT JOIN android_malware_type AS typ
    ON typ.type_id = fam.primary_type_id
LEFT JOIN android_malware_type AS parent_typ
    ON parent_typ.type_id = typ.parent_type_id
LEFT JOIN android_malware_family_alias AS alias
    ON alias.family_id = fam.family_id
   AND LOWER(TRIM(alias.alias_name)) = LOWER(TRIM(fam_norm.family_lc))
   AND alias.is_active = 1
WHERE msc.platform = 'android'
  AND msc.file_extension = 'apk'
"""

LIVE_VIEW_MISSING_WARNING = (
    "Authority view unavailable; run `database/sql/view_android_sample_family_type_authority.sql` "
    "against Erebus before using this diagnostic."
)

_LOW_TEMPORAL_COVERAGE_PCT = 80.0
_HIGH_TYPE_CONCENTRATION_PCT = 60.0


def _label_authority_logger():
    return get_logger("diagnostics.family_type_authority_coverage", "label_authority")


def _temporal_readiness_logger():
    return get_logger("diagnostics.family_type_authority_coverage", "temporal_readiness")


def _coerce_int(value: Any) -> int:
    if pd.isna(value):
        return 0
    return int(value)


def _coerce_float(value: Any) -> float:
    if pd.isna(value):
        return 0.0
    return float(value)


def _table_has_column(table_name: str, column_name: str) -> bool:
    return authority_contracts.table_has_column(table_name, column_name)


def _authority_view_fallback_sql() -> str:
    query = AUTHORITY_VIEW_SELECT
    if not _table_has_column("android_malware_family", "is_active"):
        query = query.replace("   AND fam.is_active = 1\n", "\n")
    if not _table_has_column("android_malware_family_alias", "is_active"):
        query = query.replace("   AND alias.is_active = 1\n", "\n")
    return query


def build_temporal_year_coverage(year_bucket_df: pd.DataFrame) -> pd.DataFrame:
    if year_bucket_df.empty:
        return pd.DataFrame()
    totals = year_bucket_df.groupby("sample_year", dropna=False)["row_count"].sum().rename("total_rows")
    typed = (
        year_bucket_df[year_bucket_df["authority_bucket"] == "authority_family_typed"]
        .groupby("sample_year", dropna=False)["row_count"]
        .sum()
        .rename("typed_rows")
    )
    out = pd.concat([totals, typed], axis=1).fillna(0).reset_index()
    out["typed_rows"] = out["typed_rows"].astype(int)
    out["total_rows"] = out["total_rows"].astype(int)
    out["typed_pct"] = ((out["typed_rows"] / out["total_rows"].replace(0, pd.NA)) * 100.0).fillna(0.0).round(2)
    return out.sort_values("sample_year")


def build_year_type_concentration(year_type_df: pd.DataFrame) -> pd.DataFrame:
    if year_type_df.empty:
        return pd.DataFrame()
    totals = year_type_df.groupby("sample_year")["row_count"].sum().rename("year_total_rows")
    out = year_type_df.merge(totals, on="sample_year", how="left")
    out["type_share_pct"] = ((out["row_count"] / out["year_total_rows"].replace(0, pd.NA)) * 100.0).fillna(0.0).round(2)
    return out.sort_values(["sample_year", "row_count", "type_slug"], ascending=[True, False, True])


def emit_label_authority_alerts(
    *,
    source_mode: str,
    bucket_df: pd.DataFrame,
    missing_df: pd.DataFrame,
    unknown_type_df: pd.DataFrame,
    top_conflicts_df: pd.DataFrame,
) -> None:
    logger = _label_authority_logger()
    total_rows = _coerce_int(bucket_df["row_count"].sum()) if not bucket_df.empty else 0
    typed_rows = (
        _coerce_int(bucket_df.loc[bucket_df["authority_bucket"] == "authority_family_typed", "row_count"].sum())
        if not bucket_df.empty
        else 0
    )
    log_event(
        logger,
        "label_authority_coverage_summary",
        source_mode=source_mode,
        total_rows=total_rows,
        typed_rows=typed_rows,
        typed_pct=round((typed_rows / total_rows) * 100.0, 2) if total_rows else 0.0,
        unresolved_family_rows=_coerce_int(
            bucket_df.loc[bucket_df["authority_bucket"] == "resolved_but_no_authority_family", "row_count"].sum()
        )
        if not bucket_df.empty
        else 0,
        generic_label_rows=_coerce_int(
            bucket_df.loc[bucket_df["authority_bucket"] == "generic_label_candidate", "row_count"].sum()
        )
        if not bucket_df.empty
        else 0,
        unknown_type_rows=_coerce_int(
            bucket_df.loc[bucket_df["authority_bucket"] == "authority_family_unknown_type", "row_count"].sum()
        )
        if not bucket_df.empty
        else 0,
        resolved_unknown_rows=_coerce_int(
            bucket_df.loc[bucket_df["authority_bucket"] == "resolved_unknown", "row_count"].sum()
        )
        if not bucket_df.empty
        else 0,
    )

    for _, row in bucket_df.iterrows():
        bucket = str(row["authority_bucket"])
        if bucket == "authority_family_typed":
            continue
        log_event(
            logger,
            "label_authority_bucket_alert",
            level="WARNING",
            source_mode=source_mode,
            authority_bucket=bucket,
            row_count=_coerce_int(row["row_count"]),
            row_pct=_coerce_float(row["row_pct"]),
            family_count=_coerce_int(row["family_count"]),
        )

    for _, row in missing_df.head(20).iterrows():
        log_event(
            logger,
            "missing_family_authority_candidate",
            level="WARNING",
            source_mode=source_mode,
            resolved_family_lc=str(row["resolved_family_lc"]),
            authority_gap_reason=str(row["authority_gap_reason"]),
            candidate_kind=str(row["candidate_kind"]),
            row_count=_coerce_int(row["row_count"]),
            years_present=_coerce_int(row["years_present"]),
            priority_family_curation=bool(_coerce_int(row["priority_family_curation_flag"])),
        )

    for _, row in unknown_type_df.head(20).iterrows():
        log_event(
            logger,
            "authority_family_missing_type",
            level="WARNING",
            source_mode=source_mode,
            family_slug=str(row["family_slug"]),
            family_name=str(row["family_name"]),
            row_count=_coerce_int(row["row_count"]),
            active_years=_coerce_int(row["active_years"]),
            priority_type_curation=bool(_coerce_int(row["priority_type_curation_flag"])),
        )

    for _, row in top_conflicts_df.head(20).iterrows():
        log_event(
            logger,
            "raw_authority_conflict",
            level="WARNING",
            source_mode=source_mode,
            family_slug=str(row["family_slug"]),
            type_slug=str(row["type_slug"]),
            raw_classification_primary=str(row["raw_classification_primary"]),
            raw_classification_subtype=str(row["raw_classification_subtype"]),
            row_count=_coerce_int(row["row_count"]),
        )


def emit_temporal_readiness_alerts(
    *,
    source_mode: str,
    year_bucket_df: pd.DataFrame,
    year_type_df: pd.DataFrame,
    concentration_df: pd.DataFrame,
) -> None:
    logger = _temporal_readiness_logger()
    year_coverage_df = build_temporal_year_coverage(year_bucket_df)
    year_type_concentration_df = build_year_type_concentration(year_type_df)

    log_event(
        logger,
        "temporal_readiness_summary",
        source_mode=source_mode,
        low_coverage_years=_coerce_int((year_coverage_df["typed_pct"] < _LOW_TEMPORAL_COVERAGE_PCT).sum())
        if not year_coverage_df.empty
        else 0,
        single_year_families=_coerce_int((concentration_df["temporal_feasibility"] == "single_year_only").sum())
        if not concentration_df.empty
        else 0,
        limited_persistence_families=_coerce_int(
            (concentration_df["temporal_feasibility"] == "limited_temporal_persistence").sum()
        )
        if not concentration_df.empty
        else 0,
        high_type_concentration_years=_coerce_int(
            (
                year_type_concentration_df.groupby("sample_year")["type_share_pct"].max().fillna(0.0)
                >= _HIGH_TYPE_CONCENTRATION_PCT
            ).sum()
        )
        if not year_type_concentration_df.empty
        else 0,
    )

    for _, row in year_coverage_df.iterrows():
        if _coerce_float(row["typed_pct"]) >= _LOW_TEMPORAL_COVERAGE_PCT:
            continue
        log_event(
            logger,
            "low_authority_coverage_year",
            level="WARNING",
            source_mode=source_mode,
            sample_year=_coerce_int(row["sample_year"]),
            total_rows=_coerce_int(row["total_rows"]),
            typed_rows=_coerce_int(row["typed_rows"]),
            typed_pct=_coerce_float(row["typed_pct"]),
        )

    for _, row in year_type_concentration_df.iterrows():
        if _coerce_float(row["type_share_pct"]) < _HIGH_TYPE_CONCENTRATION_PCT:
            continue
        log_event(
            logger,
            "type_year_concentration_alert",
            level="WARNING",
            source_mode=source_mode,
            sample_year=_coerce_int(row["sample_year"]),
            type_slug=str(row["type_slug"]),
            row_count=_coerce_int(row["row_count"]),
            year_total_rows=_coerce_int(row["year_total_rows"]),
            type_share_pct=_coerce_float(row["type_share_pct"]),
        )

    for _, row in concentration_df[concentration_df["temporal_feasibility"] != "multi_year_candidate"].head(25).iterrows():
        log_event(
            logger,
            "family_temporal_feasibility_alert",
            level="WARNING",
            source_mode=source_mode,
            family_slug=str(row["family_slug"]),
            type_slug=str(row["type_slug"]),
            row_count=_coerce_int(row["row_count"]),
            active_years=_coerce_int(row["active_years"]),
            min_year=_coerce_int(row["min_year"]),
            max_year=_coerce_int(row["max_year"]),
            temporal_feasibility=str(row["temporal_feasibility"]),
        )

    if not year_coverage_df.empty or not concentration_df.empty:
        log_event(
            logger,
            "temporal_split_caveat",
            level="WARNING",
            source_mode=source_mode,
            caveat=(
                "Use authority-covered, type-stratified, family-persistence-aware temporal benchmarks; "
                "global random-split-style interpretation is unsafe."
            ),
        )


def view_present() -> bool:
    return authority_contracts.authority_view_present()


def load_authority_df(*, require_live_view: bool = False) -> tuple[pd.DataFrame, str, str | None]:
    if view_present():
        df = db_engine.execute_query(
            "SELECT * FROM v_android_sample_family_type_authority",
            fetch=True,
            as_dataframe=True,
        )
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame(), "live_view", None
    if require_live_view:
        return pd.DataFrame(), "live_view_missing", LIVE_VIEW_MISSING_WARNING
    df = db_engine.execute_query(_authority_view_fallback_sql(), fetch=True, as_dataframe=True)
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame(), "embedded_sql_fallback", None


def classify_missing_candidate(token: str, gap_reason: str) -> str:
    token_lc = str(token or "").strip().lower()
    if token_lc == "unknown":
        return "unknown_label"
    if token_lc in GENERIC_OR_COARSE or gap_reason == "resolved_token_coarse_behavior":
        return "generic_or_coarse_label"
    if gap_reason == "resolved_token_malformed_or_composite":
        return "malformed_or_composite"
    if not token_lc or len(token_lc) < 3:
        return "malformed_or_composite"
    return "plausible_real_family_candidate"


def temporal_feasibility_label(active_years: int, row_count: int) -> str:
    if row_count < 10:
        return "insufficient_support"
    if active_years <= 1:
        return "single_year_only"
    if active_years == 2:
        return "limited_temporal_persistence"
    return "multi_year_candidate"


def build_bucket_summary(df: pd.DataFrame) -> pd.DataFrame:
    out = (
        df.groupby("authority_bucket")
        .agg(
            row_count=("sample_id", "count"),
            family_count=(
                "resolved_family_lc",
                lambda s: s.fillna("").astype(str).str.strip().str.lower().replace("", pd.NA).dropna().nunique(),
            ),
        )
        .reset_index()
        .sort_values(["row_count", "authority_bucket"], ascending=[False, True])
    )
    out["row_pct"] = (out["row_count"] / max(len(df), 1) * 100.0).round(2)
    return out


def build_year_summary(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = df.copy()
    work["sample_year"] = pd.to_datetime(work["vt_first_submission_at_utc"], errors="coerce").dt.year
    year_bucket = (
        work.groupby(["sample_year", "authority_bucket"])
        .size()
        .reset_index(name="row_count")
        .sort_values(["sample_year", "row_count"], ascending=[True, False])
    )
    typed = work[work["authority_bucket"] == "authority_family_typed"].copy()
    year_type = (
        typed.groupby(["sample_year", "type_slug"])
        .size()
        .reset_index(name="row_count")
        .sort_values(["sample_year", "row_count", "type_slug"], ascending=[True, False, True])
    )
    return year_bucket, year_type


def build_missing_candidates(df: pd.DataFrame) -> pd.DataFrame:
    work = df[df["authority_bucket"].isin(["resolved_but_no_authority_family", "generic_label_candidate"])].copy()
    if work.empty:
        return pd.DataFrame()
    work["candidate_kind"] = work.apply(
        lambda row: classify_missing_candidate(row.get("resolved_family_lc"), row.get("authority_gap_reason", "")),
        axis=1,
    )
    grouped = (
        work.groupby(["resolved_family_lc", "authority_gap_reason", "candidate_kind"])
        .agg(
            row_count=("sample_id", "count"),
            years_present=("vt_first_submission_at_utc", lambda s: pd.to_datetime(s, errors="coerce").dt.year.dropna().nunique()),
        )
        .reset_index()
        .sort_values(["row_count", "resolved_family_lc"], ascending=[False, True])
    )
    grouped["priority_family_curation_flag"] = (
        grouped["resolved_family_lc"].astype(str).str.lower().isin(PRIORITY_FAMILY_CURATION).astype(int)
    )
    return grouped


def build_unknown_type_queue(df: pd.DataFrame) -> pd.DataFrame:
    work = df[df["authority_bucket"] == "authority_family_unknown_type"].copy()
    if work.empty:
        return pd.DataFrame()
    grouped = (
        work.groupby(["family_slug", "family_name"])
        .agg(
            row_count=("sample_id", "count"),
            active_years=("vt_first_submission_at_utc", lambda s: pd.to_datetime(s, errors="coerce").dt.year.dropna().nunique()),
        )
        .reset_index()
        .sort_values(["row_count", "family_slug"], ascending=[False, True])
    )
    grouped["priority_type_curation_flag"] = (
        grouped["family_slug"].astype(str).str.lower().isin(PRIORITY_UNKNOWN_TYPE).astype(int)
    )
    return grouped


def build_conflict_summary(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary = (
        df.groupby("raw_vs_authority_status")
        .size()
        .reset_index(name="row_count")
        .sort_values(["row_count", "raw_vs_authority_status"], ascending=[False, True])
    )
    conflicts = df[df["raw_vs_authority_status"] == "raw_conflicts_with_authority"].copy()
    if conflicts.empty:
        top = pd.DataFrame()
    else:
        top = (
            conflicts.groupby(["family_slug", "type_slug", "raw_classification_primary", "raw_classification_subtype"])
            .size()
            .reset_index(name="row_count")
            .sort_values(["row_count", "family_slug"], ascending=[False, True])
        )
    return summary, top


def build_time_concentration(df: pd.DataFrame) -> pd.DataFrame:
    typed = df[df["authority_bucket"] == "authority_family_typed"].copy()
    if typed.empty:
        return pd.DataFrame()
    typed["sample_year"] = pd.to_datetime(typed["vt_first_submission_at_utc"], errors="coerce").dt.year
    grouped = (
        typed.groupby(["family_slug", "type_slug"])
        .agg(
            row_count=("sample_id", "count"),
            active_years=("sample_year", lambda s: s.dropna().nunique()),
            min_year=("sample_year", "min"),
            max_year=("sample_year", "max"),
        )
        .reset_index()
        .sort_values(["row_count", "family_slug"], ascending=[False, True])
    )
    grouped["temporal_feasibility"] = grouped.apply(
        lambda row: temporal_feasibility_label(int(row["active_years"]), int(row["row_count"])),
        axis=1,
    )
    return grouped


def write_report(
    *,
    df: pd.DataFrame,
    source_mode: str,
    bucket_df: pd.DataFrame,
    year_bucket_df: pd.DataFrame,
    missing_df: pd.DataFrame,
    unknown_type_df: pd.DataFrame,
    conflict_summary_df: pd.DataFrame,
    top_conflicts_df: pd.DataFrame,
    concentration_df: pd.DataFrame,
    md_path: Path,
) -> None:
    plausible_missing_df = (
        missing_df[missing_df["candidate_kind"] == "plausible_real_family_candidate"].copy()
        if not missing_df.empty
        else pd.DataFrame()
    )
    policy_held_df = (
        missing_df[missing_df["candidate_kind"] == "generic_or_coarse_label"].copy()
        if not missing_df.empty
        else pd.DataFrame()
    )
    lines = [
        "# Family/Type Authority Coverage Report",
        "",
        f"- Source mode: `{source_mode}`",
        f"- Android APK rows evaluated: `{len(df)}`",
        "",
        "## Authority Bucket Summary",
        "",
        "| authority_bucket | row_count | row_pct | family_count |",
        "|---|---:|---:|---:|",
    ]
    for _, row in bucket_df.iterrows():
        lines.append(
            f"| `{row['authority_bucket']}` | {int(row['row_count'])} | {row['row_pct']:.2f} | {int(row['family_count'])} |"
        )

    lines.extend(
        [
            "",
            "## Raw-vs-Authority Status Summary",
            "",
            "| status | row_count |",
            "|---|---:|",
        ]
    )
    for _, row in conflict_summary_df.iterrows():
        lines.append(f"| `{row['raw_vs_authority_status']}` | {int(row['row_count'])} |")

    if not plausible_missing_df.empty:
        lines.extend(
            [
                "",
                "## True Missing Authority-Family Candidates",
                "",
                "| resolved_family_lc | gap_reason | row_count | years_present | priority |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for _, row in plausible_missing_df.head(25).iterrows():
            lines.append(
                f"| `{row['resolved_family_lc']}` | `{row['authority_gap_reason']}` | "
                f"{int(row['row_count'])} | {int(row['years_present'])} | {int(row['priority_family_curation_flag'])} |"
            )

    if not policy_held_df.empty:
        lines.extend(
            [
                "",
                "## Policy-Held Generic/Coarse Token Residue",
                "",
                "| resolved_family_lc | gap_reason | row_count | years_present | priority |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for _, row in policy_held_df.head(25).iterrows():
            lines.append(
                f"| `{row['resolved_family_lc']}` | `{row['authority_gap_reason']}` | "
                f"{int(row['row_count'])} | {int(row['years_present'])} | {int(row['priority_family_curation_flag'])} |"
            )

    if not unknown_type_df.empty:
        lines.extend(
            [
                "",
                "## Authority Families With Unknown Type",
                "",
                "| family_slug | family_name | row_count | active_years | priority |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for _, row in unknown_type_df.head(25).iterrows():
            lines.append(
                f"| `{row['family_slug']}` | `{row['family_name']}` | {int(row['row_count'])} | "
                f"{int(row['active_years'])} | {int(row['priority_type_curation_flag'])} |"
            )

    if not top_conflicts_df.empty:
        lines.extend(
            [
                "",
                "## Top Raw-vs-Authority Conflicts",
                "",
                "| family_slug | type_slug | raw_primary | raw_subtype | row_count |",
                "|---|---|---|---|---:|",
            ]
        )
        for _, row in top_conflicts_df.head(20).iterrows():
            lines.append(
                f"| `{row['family_slug']}` | `{row['type_slug']}` | `{row['raw_classification_primary']}` | "
                f"`{row['raw_classification_subtype']}` | {int(row['row_count'])} |"
            )

    if not concentration_df.empty:
        lines.extend(
            [
                "",
                "## Time Concentration By Authority Family",
                "",
                "| family_slug | type_slug | row_count | active_years | min_year | max_year | feasibility |",
                "|---|---|---:|---:|---:|---:|---|",
            ]
        )
        for _, row in concentration_df.head(25).iterrows():
            lines.append(
                f"| `{row['family_slug']}` | `{row['type_slug']}` | {int(row['row_count'])} | {int(row['active_years'])} | "
                f"{int(row['min_year']) if pd.notna(row['min_year']) else ''} | {int(row['max_year']) if pd.notna(row['max_year']) else ''} | `{row['temporal_feasibility']}` |"
            )

    if not year_bucket_df.empty:
        lines.extend(
            [
                "",
                "## Temporal Split Recommendation",
                "",
                "- Use an authority-covered temporal benchmark, not the whole catalog.",
                "- Add a type-stratified temporal benchmark because year/type concentration is high.",
                "- Add a family-persistence-only benchmark for families with multi-year support.",
            ]
        )

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_authority_coverage_artifacts(
    *,
    md_path: Path = DEFAULT_MD,
    missing_out: Path = DEFAULT_MISSING,
    unknown_type_out: Path = DEFAULT_UNKNOWN_TYPE,
    year_type_out: Path = DEFAULT_YEAR_TYPE,
    require_live_view: bool = False,
) -> dict[str, Any]:
    df, source_mode, warning = load_authority_df(require_live_view=require_live_view)
    if df.empty:
        return {
            "ok": False,
            "source_mode": source_mode,
            "warning": warning or "[WARN] No authority rows returned.",
            "df": df,
        }

    bucket_df = build_bucket_summary(df)
    year_bucket_df, year_type_df = build_year_summary(df)
    missing_df = build_missing_candidates(df)
    unknown_type_df = build_unknown_type_queue(df)
    conflict_summary_df, top_conflicts_df = build_conflict_summary(df)
    concentration_df = build_time_concentration(df)

    missing_out.parent.mkdir(parents=True, exist_ok=True)
    missing_df.to_csv(missing_out, index=False)
    unknown_type_df.to_csv(unknown_type_out, index=False)
    year_type_df.to_csv(year_type_out, index=False)
    emit_label_authority_alerts(
        source_mode=source_mode,
        bucket_df=bucket_df,
        missing_df=missing_df,
        unknown_type_df=unknown_type_df,
        top_conflicts_df=top_conflicts_df,
    )
    emit_temporal_readiness_alerts(
        source_mode=source_mode,
        year_bucket_df=year_bucket_df,
        year_type_df=year_type_df,
        concentration_df=concentration_df,
    )
    write_report(
        df=df,
        source_mode=source_mode,
        bucket_df=bucket_df,
        year_bucket_df=year_bucket_df,
        missing_df=missing_df,
        unknown_type_df=unknown_type_df,
        conflict_summary_df=conflict_summary_df,
        top_conflicts_df=top_conflicts_df,
        concentration_df=concentration_df,
        md_path=md_path,
    )
    return {
        "ok": True,
        "source_mode": source_mode,
        "warning": warning,
        "df": df,
        "bucket_df": bucket_df,
        "year_bucket_df": year_bucket_df,
        "year_type_df": year_type_df,
        "missing_df": missing_df,
        "unknown_type_df": unknown_type_df,
        "conflict_summary_df": conflict_summary_df,
        "top_conflicts_df": top_conflicts_df,
        "concentration_df": concentration_df,
        "md_path": md_path,
        "missing_out": missing_out,
        "unknown_type_out": unknown_type_out,
        "year_type_out": year_type_out,
    }


__all__ = [
    "AUTHORITY_VIEW_SELECT",
    "DEFAULT_MD",
    "DEFAULT_MISSING",
    "DEFAULT_UNKNOWN_TYPE",
    "DEFAULT_YEAR_TYPE",
    "LIVE_VIEW_MISSING_WARNING",
    "build_bucket_summary",
    "build_conflict_summary",
    "build_missing_candidates",
    "build_temporal_year_coverage",
    "build_time_concentration",
    "build_unknown_type_queue",
    "build_year_type_concentration",
    "build_year_summary",
    "classify_missing_candidate",
    "emit_label_authority_alerts",
    "emit_temporal_readiness_alerts",
    "generate_authority_coverage_artifacts",
    "load_authority_df",
    "temporal_feasibility_label",
    "view_present",
    "write_report",
]
