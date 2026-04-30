"""Readiness summary utilities for taxonomy-driven training cohorts."""

from __future__ import annotations

import pandas as pd
from config import app_config
from utils import display_utils as du


def print_cohort_readiness_report(
    samples_df: pd.DataFrame,
    gates: dict | None = None,
) -> None:
    """Print a compact cohort-quality report before training.

    Args:
        samples_df: Prepared metadata DataFrame for pipeline execution.
        gates: Optional cohort gate config used for threshold/policy context.
    """
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        du.print_warning("[COHORT] No cohort data available for readiness summary.")
        return

    gates = gates if isinstance(gates, dict) else {}
    total = len(samples_df)
    missing_pkg = _missing_ratio(samples_df, "android_package_name", fallback="package_name")
    missing_vt_time = _missing_vt_time_ratio(samples_df)
    unmapped = _unmapped_count(samples_df)
    fam_col = _family_column(samples_df)

    du.print_section("Cohort Readiness Summary")
    du.print_stat("Final Samples", f"{total:,}")
    du.print_stat("Unique Families", _unique_count(samples_df, fam_col))
    du.print_stat("Represented Types", _unique_count(samples_df, "type_slug"))

    du.print_subheader("Quality Checks")
    du.print_stat("Unmapped Labels", unmapped)
    max_missing_pkg_pct = float(gates.get("max_missing_package_pct", 10.0))
    pkg_label = f"{missing_pkg:.2f}%"
    if missing_pkg > max_missing_pkg_pct:
        pkg_label += f" (threshold {max_missing_pkg_pct:.2f}%)"
    du.print_stat("Missing Package Name", pkg_label)
    du.print_stat("Missing VT Timestamps", f"{missing_vt_time:.2f}%")

    if "type_slug" in samples_df.columns:
        counts = samples_df["type_slug"].fillna("unknown").value_counts()
        du.print_subheader("Type Distribution")
        for key, value in counts.items():
            pct = (float(value) / max(total, 1)) * 100.0
            du.print_info(f"  - {key}: {value:,} ({pct:.2f}%)")

    if fam_col:
        fam_counts = samples_df[fam_col].fillna("unknown").value_counts()
        top_family = str(fam_counts.index[0]) if len(fam_counts) else "n/a"
        top_family_count = int(fam_counts.iloc[0]) if len(fam_counts) else 0
        top_family_share = (float(top_family_count) / max(total, 1)) * 100.0
        top3 = int(fam_counts.head(3).sum()) if len(fam_counts) else 0
        top5 = int(fam_counts.head(5).sum()) if len(fam_counts) else 0
        du.print_subheader("Family Concentration")
        du.print_stat(
            "Top Family",
            f"{top_family} ({top_family_count:,}, {top_family_share:.2f}%)",
        )
        du.print_stat(
            "Top 3 Families",
            f"{top3:,} ({(float(top3) / max(total, 1)) * 100.0:.2f}%)",
        )
        du.print_stat(
            "Top 5 Families",
            f"{top5:,} ({(float(top5) / max(total, 1)) * 100.0:.2f}%)",
        )

        du.print_subheader("Top Families (Top 10)")
        for key, value in fam_counts.head(10).items():
            du.print_info(f"  - {key}: {int(value):,}")

    _print_cohort_policy(samples_df=samples_df, gates=gates)
    _print_cohort_verdict(
        total=total,
        missing_pkg=missing_pkg,
        max_missing_pkg_pct=max_missing_pkg_pct,
        fam_col=fam_col,
        samples_df=samples_df,
    )


def print_cohort_gate_stats(stats: dict) -> None:
    """Print gate-level inclusion/exclusion counts for a planned cohort."""
    if not isinstance(stats, dict) or not stats:
        return

    du.print_section("Cohort Gate Stats")
    du.print_stat("Type Slug", stats.get("type_slug", "unknown"))
    du.print_stat("Total Candidates", int(stats.get("total_candidates", 0)))
    du.print_stat("Excluded Unmapped Family", int(stats.get("excluded_unmapped_family", 0)))
    du.print_stat("Excluded Missing SHA256", int(stats.get("excluded_missing_sha256", 0)))
    du.print_stat("Excluded Unknown Type", int(stats.get("excluded_unknown_type_slug", 0)))
    du.print_stat("Excluded Missing Package", int(stats.get("excluded_missing_package_name", 0)))
    du.print_stat("Excluded Low Support", int(stats.get("excluded_low_support", 0)))
    du.print_stat("Final Count (Estimate)", int(stats.get("final_count_estimate", 0)))


def _family_column(df: pd.DataFrame) -> str | None:
    for col in ("family_canonical", "family_name", "family_label_raw"):
        if col in df.columns:
            return col
    return None


def _missing_ratio(df: pd.DataFrame, primary: str, fallback: str | None = None) -> float:
    col = primary if primary in df.columns else fallback
    if col is None or col not in df.columns:
        return 100.0
    missing = df[col].isnull() | (df[col].astype(str).str.strip() == "")
    return float(missing.mean() * 100.0)


def _missing_vt_time_ratio(df: pd.DataFrame) -> float:
    sub_col = "vt_first_submission_date" if "vt_first_submission_date" in df.columns else None
    itw_col = "vt_first_seen_itw_date" if "vt_first_seen_itw_date" in df.columns else None
    if not sub_col and not itw_col:
        return 100.0

    if sub_col and itw_col:
        missing = df[sub_col].isnull() & df[itw_col].isnull()
    else:
        use_col = sub_col or itw_col
        missing = df[use_col].isnull()
    return float(missing.mean() * 100.0)


def _unmapped_count(df: pd.DataFrame) -> int:
    if "family_id" in df.columns:
        return int(df["family_id"].isnull().sum())
    if "family_canonical" in df.columns:
        return int((df["family_canonical"].isnull() | (df["family_canonical"].astype(str).str.strip() == "")).sum())
    return 0


def _unique_count(df: pd.DataFrame, col: str | None) -> int:
    """Count non-empty unique values for a given column."""
    if not col or col not in df.columns:
        return 0
    series = df[col].fillna("").astype(str).str.strip()
    return int(series[series != ""].nunique())


def _print_cohort_policy(samples_df: pd.DataFrame, gates: dict) -> None:
    """Print active cohort policy knobs for reproducibility readability."""
    excluded = samples_df.attrs.get("sql_exclude_families_applied", ())
    min_support = int(
        gates.get(
            "min_samples_per_family",
            getattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", getattr(app_config, "MIN_FAMILY_SUPPORT", 3)),
        )
        or 3
    )
    exclude_unknown = bool(gates.get("exclude_unknown_type_slug", False))
    du.print_subheader("Cohort Policy")
    excluded_txt = ", ".join([str(x) for x in excluded]) if excluded else "(none)"
    du.print_stat("Excluded Families", excluded_txt)
    du.print_stat("Excluded Types", "unknown" if exclude_unknown else "(none)")
    du.print_stat("Minimum Family Support", min_support)


def _print_cohort_verdict(
    *,
    total: int,
    missing_pkg: float,
    max_missing_pkg_pct: float,
    fam_col: str | None,
    samples_df: pd.DataFrame,
) -> None:
    """Emit one-line readiness verdict for testers and paper drafting."""
    top_family_share = 0.0
    if fam_col and fam_col in samples_df.columns and total > 0:
        fam_counts = samples_df[fam_col].fillna("unknown").value_counts()
        if len(fam_counts):
            top_family_share = float(fam_counts.iloc[0]) / float(total)
    banker_share = 0.0
    if "type_slug" in samples_df.columns and total > 0:
        type_counts = samples_df["type_slug"].fillna("unknown").astype(str).str.lower().value_counts()
        banker_share = float(type_counts.get("banker", 0)) / float(total)

    warn = (
        missing_pkg > max_missing_pkg_pct
        or top_family_share >= 0.30
        or banker_share >= 0.60
    )
    if warn:
        du.print_warning(
            "[COHORT] Cohort is usable but remains concentration-heavy and/or has notable missingness."
        )
    else:
        du.print_info("[COHORT] Filtered multi-type malware cohort ready for downstream analysis.")
