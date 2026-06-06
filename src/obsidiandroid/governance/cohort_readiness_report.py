"""Readiness summaries and SQL-scope gate diagnostics for training cohorts.

Operator vocabulary (see ``obsidiandroid.diagnostics.cohort_vocabulary``):

* **SQL profile scope** — database head count before rows are materialized into ``samples_df``.
* **Prepared cohort** — rows in ``samples_df`` after fetch + Python preparation.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console
from obsidiandroid.diagnostics import taxonomy_target_surface_report
from obsidiandroid.governance.evidence_mode_resolver import coalesce_manifest_evidence_mode
from obsidiandroid.governance.support_floor_policy import (
    SUPPORT_DIAGNOSTIC_FLOORS,
    resolve_configured_min_samples_per_family,
    resolve_diagnostic_min_samples_per_family,
    resolve_support_floor_mode,
)


def _coalesce_attrs_publication_mode(samples_df: pd.DataFrame) -> bool:
    """Resolve publication/evidence mode from ``samples_df.attrs`` without dict truthiness bugs."""
    attrs = samples_df.attrs if hasattr(samples_df, "attrs") else {}
    for key in ("publication_ready_mode", "evidence_mode"):
        payload = attrs.get(key)
        if coalesce_manifest_evidence_mode(payload):
            return True
    return bool(getattr(app_config, "EVIDENCE_MODE_ENABLED", False))


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
    gate_stats: dict = {}
    if hasattr(samples_df, "attrs") and isinstance(getattr(samples_df, "attrs", None), dict):
        raw_stats = samples_df.attrs.get("cohort_gate_stats")
        if isinstance(raw_stats, dict):
            gate_stats = raw_stats

    missing_pkg = _missing_ratio(samples_df, "android_package_name", fallback="package_name")
    missing_vt_time = _missing_vt_time_ratio(samples_df)
    unmapped = _unmapped_count(samples_df)
    max_missing_pkg_pct = float(gates.get("max_missing_package_pct", 10.0))
    fam_col = _family_column(samples_df)
    sql_scope_total = int(gate_stats.get("total_candidates") or 0)
    governed_ref = int(gate_stats.get("governed_cohort_count") or gate_stats.get("final_count_estimate") or 0)
    profile_id = str(
        samples_df.attrs.get("profile_id")
        or getattr(app_config, "RUNTIME_PROFILE_ID", "")
        or ""
    ).strip()
    heading = _cohort_summary_heading(profile_id=profile_id, samples_df=samples_df)
    du.print_section(heading)

    target_summary = _build_target_surface_summary(samples_df, gates=gates)
    composition = _build_composition_summary(samples_df=samples_df, fam_col=fam_col, total=total)
    quality = _build_catalog_quality_metrics(
        samples_df=samples_df,
        total=total,
        missing_pkg=missing_pkg,
        missing_vt_time=missing_vt_time,
        unmapped=unmapped,
    )
    drift_groups = _collect_top_drift_groups(samples_df)

    funnel_sql = sql_scope_total if sql_scope_total > 0 else total
    funnel_governed = governed_ref if governed_ref > 0 else total
    support_floor_mode = resolve_support_floor_mode(gates, samples_df=samples_df)
    funnel_trainable_rows = int(target_summary.get("benchmark_eligible_rows", total) or 0)
    represented_types = _unique_count(samples_df, "type_slug")
    represented_families = _unique_count(samples_df, fam_col)
    benchmark_trainable_families = int(target_summary.get("family_trainable_classes", 0) or 0)
    benchmark_floor = target_summary.get("benchmark_min_support")
    conservative_families = int(target_summary.get("family_trainable_classes_at_20", 0) or 0)
    support_excluded_rows = max(0, total - funnel_trainable_rows)
    support_excluded_families = max(0, represented_families - benchmark_trainable_families)

    surface_label = _profile_surface_label(profile_id=profile_id, samples_df=samples_df)
    du.print_stat("Profile surface", surface_label)
    if support_floor_mode == "diagnostic_only":
        funnel_tail = f"{total:,} prepared (diagnostic; classifier pool may be smaller after family-authority filter)"
    elif support_floor_mode == "benchmark_eligibility":
        funnel_tail = f"{funnel_trainable_rows:,} benchmark-trainable"
    else:
        funnel_tail = f"{funnel_trainable_rows:,} trainable"
    du.print_stat(
        "Cohort funnel",
        f"{funnel_sql:,} SQL → {funnel_governed:,} governed → {total:,} prepared → {funnel_tail}",
    )
    if benchmark_floor not in (None, ""):
        du.print_stat(
            "Benchmark trainable",
            f"{funnel_trainable_rows:,} rows | {benchmark_trainable_families:,} families after n>={int(benchmark_floor)} support gate",
        )
        du.print_stat(
            "Diagnostic-only rows",
            f"{support_excluded_rows:,} rows | {support_excluded_families:,} families below support threshold",
        )
    du.print_stat(
        "Represented taxonomy",
        f"{represented_types:,} type_slug classes | {represented_families:,} visible families",
    )

    du.print_subheader("Benchmark Targets")
    du.print_stat(
        "Family target",
        f"family_id | {benchmark_trainable_families:,} benchmark-eligible classes",
    )
    if support_floor_mode == "diagnostic_only":
        du.print_stat(
            "Actual modeled family classes",
            f"family_id | {represented_families:,} diagnostic modeled classes",
        )
    du.print_stat(
        "Type target",
        f"type_slug | {int(target_summary.get('type_trainable_classes', 0) or 0):,} trainable classes",
    )
    du.print_stat(
        "Family-within-type",
        f"{int(target_summary.get('family_within_type_trainable_classes', 0) or 0):,} trainable classes",
    )
    du.print_stat("Raw label fields", "audit only; not primary scientific targets")

    du.print_subheader("Cohort Composition")
    if composition.get("top_types"):
        du.print_stat("Top types", str(composition["top_types"]))
    if composition.get("top_families"):
        du.print_stat("Top families", str(composition["top_families"]))
    if composition.get("concentration"):
        du.print_stat("Concentration", str(composition["concentration"]))

    du.print_subheader("Quality / Risk Flags")
    du.print_stat(
        "Label readiness",
        (
            f"unmapped={int(quality['unmapped'])} | "
            f"weak labels={int(quality['weak_label_rows'])} | "
            f"non-family-target={int(target_summary.get('non_family_target_rows', 0) or 0)}"
        ),
    )
    du.print_stat(
        "Missingness",
        f"package_name missing={missing_pkg:.2f}% | VT timestamp missing={missing_vt_time:.2f}%",
    )
    if quality["all_zero_hygiene"]:
        du.print_stat(
            "Catalog hygiene",
            "no non-Android rows, weak labels, filename/hash labels, or blank VT-token rows",
        )
    elif quality.get("catalog_drift_summary"):
        du.print_stat("Catalog drift", str(quality["catalog_drift_summary"]))
    if int(quality["family_conflict_rows"]) > 0:
        du.print_stat("Family conflicts", f"raw-vs-canonical conflicts={int(quality['family_conflict_rows'])}")
    if composition.get("dominance_warning"):
        du.print_stat("Dominance warning", str(composition["dominance_warning"]))

    if drift_groups:
        du.print_subheader("Top Curation Queue")
        for idx, row in enumerate(drift_groups[:3], start=1):
            du.print_stat(
                f"{idx}. {row['label']} {row['group_value']}",
                f"{int(row['rows'])} rows",
            )

    du.print_subheader("Policy")
    if benchmark_floor not in (None, ""):
        du.print_stat("Family support rule", f"n>={int(benchmark_floor)} for supervised family benchmarking")
    if conservative_families > 0:
        du.print_stat("Conservative threshold", f"n>=20 keeps {conservative_families:,} families")
    du.print_stat("Below-threshold families", "retained in diagnostics, excluded from benchmark training")
    du.print_stat("Excluded type_slug values", "unknown" if bool(gates.get("exclude_unknown_type_slug", False)) else "(none)")
    du.print_stat("Full catalog/SQL audit", "see cohort_population_audit.csv and dataset_quality_gates.csv")

    warning_messages = _print_cohort_verdict(
        total=total,
        missing_pkg=missing_pkg,
        max_missing_pkg_pct=max_missing_pkg_pct,
        fam_col=fam_col,
        samples_df=samples_df,
    )
    if hasattr(samples_df, "attrs") and isinstance(samples_df.attrs, dict):
        samples_df.attrs["cohort_operational_warnings"] = list(warning_messages)


def print_cohort_sql_scope_gate_summary(stats: dict) -> None:
    """Print SQL-scope inclusion/exclusion counts (same semantics as ``get_type_cohort_gate_stats``)."""
    if not isinstance(stats, dict) or not stats:
        return

    du.print_section("Cohort SQL scope (gate stats)")
    du.print_stat("Type Slug", stats.get("type_slug", "unknown"))
    du.print_stat("SQL profile scope (head count)", int(stats.get("total_candidates", 0)))
    du.print_stat("Excluded Unmapped Family", int(stats.get("excluded_unmapped_family", 0)))
    du.print_stat("Excluded Missing SHA256", int(stats.get("excluded_missing_sha256", 0)))
    du.print_stat("Excluded Unknown Type", int(stats.get("excluded_unknown_type_slug", 0)))
    du.print_stat("Excluded Missing Package", int(stats.get("excluded_missing_package_name", 0)))
    if "excluded_weak_label_kind" in stats:
        du.print_stat("Excluded Weak Label Kind", int(stats.get("excluded_weak_label_kind", 0)))
    if "excluded_family_label_conflict" in stats:
        du.print_stat("Excluded Family Conflict", int(stats.get("excluded_family_label_conflict", 0)))
    if not bool(stats.get("min_samples_per_family_applied_in_sql", True)):
        low_support_txt = "diagnostic only / not applied"
    else:
        low_support_txt = str(int(stats.get("excluded_low_support", 0)))
    du.print_stat("Excluded Low Support", low_support_txt)
    governed = int(stats.get("governed_cohort_count", stats.get("final_count_estimate", 0)))
    du.print_stat("SQL governed rows", governed)
    if str(stats.get("gate_stats_mode", "") or "").strip().lower() == "derived_from_loaded_governed_frame":
        du.print_note(
            "[COHORT] SQL gate summary reused the fetched governed cohort to avoid a duplicate prefetch scan."
        )
    legacy = stats.get("final_count_estimate_sequential_legacy")
    if legacy is not None and int(legacy) != governed:
        du.print_info(
            f"[COHORT] Sequential marginal estimate was {int(legacy)} "
            f"(overlapping exclusion buckets — use governed SQL count above)."
        )


def _cohort_summary_heading(*, profile_id: str, samples_df: pd.DataFrame) -> str:
    publication_mode = _coalesce_attrs_publication_mode(samples_df)
    if publication_mode:
        return "Locked Publication Cohort Summary"
    if profile_id == "android_malware_all_current":
        return "Current-Corpus Cohort Summary"
    return "Cohort Benchmark Summary"


def _profile_surface_label(*, profile_id: str, samples_df: pd.DataFrame) -> str:
    if _coalesce_attrs_publication_mode(samples_df):
        return "Locked publication cohort"
    if profile_id == "android_malware_all_current":
        return "Current Android malware corpus"
    return "Support-gated governed major-family benchmark"


def _build_target_surface_summary(samples_df: pd.DataFrame, gates: dict) -> dict[str, Any]:
    diagnostic_min_support = resolve_diagnostic_min_samples_per_family(gates)
    summary = taxonomy_target_surface_report.build_taxonomy_target_surface_summary(
        samples_df,
        min_support=diagnostic_min_support,
    )
    targets = {
        str(row.get("surface_name", "")): row
        for row in summary.get("targets", [])
        if isinstance(row, dict)
    }
    tier_counts = summary.get("tier_counts", {}) if isinstance(summary.get("tier_counts"), dict) else {}
    benchmark_policy = (
        summary.get("benchmark_support_policy")
        if isinstance(summary.get("benchmark_support_policy"), dict)
        else {}
    )
    family_row = targets.get("family_id", {})
    type_row = targets.get("type_slug", {})
    fwt_row = targets.get("family_within_type", {})
    fam_col = _family_column(samples_df)
    support_rows = [row for row in summary.get("support_diagnostics", []) if isinstance(row, dict)]
    family_at_20 = next(
        (int(row.get("family_target_family_count", 0) or 0) for row in support_rows if int(row.get("support_floor", 0)) == 20),
        0,
    )
    benchmark_min_support = benchmark_policy.get("benchmark_min_support")
    if benchmark_min_support in (None, ""):
        benchmark_min_support = resolve_configured_min_samples_per_family(gates)
    family_trainable = int(family_row.get("trainable_classes_at_min_support", 0) or 0)
    if family_trainable == 0:
        fam_col = _family_column(samples_df)
        if fam_col and fam_col in samples_df.columns and benchmark_min_support not in (None, ""):
            fam_counts = samples_df[fam_col].fillna("").astype(str).str.strip()
            fam_counts = fam_counts[fam_counts != ""].value_counts()
            family_trainable = int((fam_counts >= int(benchmark_min_support)).sum())
            if family_at_20 == 0:
                family_at_20 = int((fam_counts >= 20).sum())
    type_trainable = int(type_row.get("trainable_classes_at_min_support", 0) or 0)
    if type_trainable == 0 and "type_slug" in samples_df.columns:
        type_counts = (
            samples_df["type_slug"].fillna("").astype(str).str.strip()
        )
        type_counts = type_counts[type_counts != ""].value_counts()
        if benchmark_min_support not in (None, ""):
            type_trainable = int((type_counts >= int(benchmark_min_support)).sum())
        else:
            type_trainable = int(type_counts.nunique())
    fwt_trainable = int(fwt_row.get("trainable_classes_at_min_support", 0) or 0)
    if fwt_trainable == 0 and {"type_slug"}.issubset(samples_df.columns):
        if fam_col and fam_col in samples_df.columns:
            pairs = (
                samples_df[["type_slug", fam_col]]
                .fillna("")
                .astype(str)
                .apply(lambda col: col.str.strip())
            )
            pairs = pairs[(pairs["type_slug"] != "") & (pairs[fam_col] != "")]
            if not pairs.empty:
                pair_counts = pairs.value_counts()
                if benchmark_min_support not in (None, ""):
                    fwt_trainable = int((pair_counts >= int(benchmark_min_support)).sum())
                else:
                    fwt_trainable = int(pair_counts.shape[0])
    non_family_target_rows = int(tier_counts.get("excluded_non_family_target_samples", 0) or 0)
    if fam_col and fam_col in samples_df.columns:
        family_present_rows = int(
            (
                samples_df[fam_col]
                .fillna("")
                .astype(str)
                .str.strip()
                .ne("")
            ).sum()
        )
        if family_present_rows > 0 and non_family_target_rows >= len(samples_df):
            non_family_target_rows = 0
    return {
        "benchmark_min_support": benchmark_min_support,
        "family_trainable_classes": family_trainable,
        "type_trainable_classes": type_trainable,
        "family_within_type_trainable_classes": fwt_trainable,
        "benchmark_eligible_rows": int(tier_counts.get("benchmark_eligible_samples", len(samples_df)) or len(samples_df)),
        "non_family_target_rows": non_family_target_rows,
        "family_trainable_classes_at_20": family_at_20,
    }


def _build_composition_summary(*, samples_df: pd.DataFrame, fam_col: str | None, total: int) -> dict[str, str]:
    result: dict[str, str] = {}
    if "type_slug" in samples_df.columns:
        counts = samples_df["type_slug"].fillna("unknown").astype(str).value_counts()
        entries = [
            f"{key}={int(value):,} ({(float(value) / max(total, 1)) * 100.0:.2f}%)"
            for key, value in counts.head(3).items()
        ]
        if entries:
            result["top_types"] = " | ".join(entries)
        banker_share = (float(counts.get("banker", 0)) / max(total, 1)) * 100.0
        if banker_share >= 60.0:
            result["dominance_warning"] = "banker share is high; lead with Macro-F1 and recall tails"
    if fam_col and fam_col in samples_df.columns:
        fam_counts = samples_df[fam_col].fillna("unknown").value_counts()
        top_families = [f"{key}={int(value):,}" for key, value in fam_counts.head(5).items()]
        if top_families:
            result["top_families"] = " | ".join(top_families)
        if len(fam_counts):
            top_family_count = int(fam_counts.iloc[0])
            top3 = int(fam_counts.head(3).sum())
            top5 = int(fam_counts.head(5).sum())
            result["concentration"] = (
                f"top family={(float(top_family_count) / max(total, 1)) * 100.0:.2f}% | "
                f"top-3={(float(top3) / max(total, 1)) * 100.0:.2f}% | "
                f"top-5={(float(top5) / max(total, 1)) * 100.0:.2f}%"
            )
    return result


def _build_catalog_quality_metrics(
    *,
    samples_df: pd.DataFrame,
    total: int,
    missing_pkg: float,
    missing_vt_time: float,
    unmapped: int,
) -> dict[str, Any]:
    lane_norm = (
        samples_df["analysis_lane"].fillna("").astype(str).str.strip().str.lower()
        if "analysis_lane" in samples_df.columns
        else pd.Series([""] * len(samples_df), index=samples_df.index, dtype="object")
    )
    target_norm = (
        samples_df["payload_target_platform"].fillna("").astype(str).str.strip().str.lower()
        if "payload_target_platform" in samples_df.columns
        else pd.Series([""] * len(samples_df), index=samples_df.index, dtype="object")
    )
    label_kind_norm = (
        samples_df["sample_label_kind"].fillna("").astype(str).str.strip().str.lower()
        if "sample_label_kind" in samples_df.columns
        else pd.Series([""] * len(samples_df), index=samples_df.index, dtype="object")
    )
    token_norm = (
        samples_df["vt_family_token"].fillna("").astype(str).str.strip()
        if "vt_family_token" in samples_df.columns
        else pd.Series([""] * len(samples_df), index=samples_df.index, dtype="object")
    )
    family_raw = (
        samples_df["family_label_raw"].fillna("").astype(str).str.strip().str.lower()
        if "family_label_raw" in samples_df.columns
        else pd.Series([""] * len(samples_df), index=samples_df.index, dtype="object")
    )
    family_canonical = (
        samples_df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
        if "family_canonical" in samples_df.columns
        else pd.Series([""] * len(samples_df), index=samples_df.index, dtype="object")
    )
    non_android_lane_rows = int((lane_norm != "android_artifact").sum()) if len(lane_norm) else 0
    non_android_target_rows = int(((target_norm != "") & (target_norm != "android")).sum()) if len(target_norm) else 0
    weak_label_rows = int(
        (
            label_kind_norm.isin({"filename", "hash_like", "opaque_string", "unclassified"})
            & ~family_canonical.isin({"", "unknown", "other", "unmapped", "none", "null"})
        ).sum()
    ) if len(label_kind_norm) else 0
    filename_rows = int((label_kind_norm == "filename").sum()) if len(label_kind_norm) else 0
    hash_rows = int((label_kind_norm == "hash_like").sum()) if len(label_kind_norm) else 0
    blank_family_with_token_rows = int(
        (
            (token_norm != "")
            & family_raw.isin({"", "unknown", "generic", "unclassified", "unlabeled"})
        ).sum()
    ) if len(token_norm) else 0
    family_conflict_rows = int(
        (
            ~family_raw.isin({"", "unknown", "generic", "unclassified", "unlabeled"})
            & ~family_canonical.isin({"", "unknown", "other", "unmapped", "none", "null"})
            & (family_raw != family_canonical)
        ).sum()
    ) if len(family_raw) else 0
    drift_parts: list[str] = []
    if non_android_lane_rows > 0:
        drift_parts.append(f"non-Android lane={non_android_lane_rows}")
    if non_android_target_rows > 0:
        drift_parts.append(f"non-Android target={non_android_target_rows}")
    if filename_rows > 0:
        drift_parts.append(f"filename labels={filename_rows}")
    if hash_rows > 0:
        drift_parts.append(f"hash labels={hash_rows}")
    if weak_label_rows > 0 and "weak labels=" + str(weak_label_rows) not in drift_parts:
        drift_parts.append(f"weak labels={weak_label_rows}")
    if blank_family_with_token_rows > 0:
        drift_parts.append(f"blank raw + VT token={blank_family_with_token_rows}")
    return {
        "unmapped": unmapped,
        "missing_pkg": missing_pkg,
        "missing_vt_time": missing_vt_time,
        "non_android_lane_rows": non_android_lane_rows,
        "non_android_target_rows": non_android_target_rows,
        "weak_label_rows": weak_label_rows,
        "filename_rows": filename_rows,
        "hash_rows": hash_rows,
        "blank_family_with_token_rows": blank_family_with_token_rows,
        "family_conflict_rows": family_conflict_rows,
        "catalog_drift_summary": " | ".join(drift_parts),
        "all_zero_hygiene": all(
            value == 0
            for value in (
                non_android_lane_rows,
                non_android_target_rows,
                weak_label_rows,
                filename_rows,
                hash_rows,
                blank_family_with_token_rows,
            )
        ),
    }


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


def _print_taxonomy_target_surfaces(samples_df: pd.DataFrame, *, gates: dict) -> None:
    """Print compact supervision-surface coverage for family/type/taxonomy targets."""
    configured_min_support = resolve_configured_min_samples_per_family(gates)
    diagnostic_min_support = resolve_diagnostic_min_samples_per_family(gates)
    summary = taxonomy_target_surface_report.build_taxonomy_target_surface_summary(
        samples_df,
        min_support=diagnostic_min_support,
    )
    targets = {
        str(row.get("surface_name", "")): row
        for row in summary.get("targets", [])
        if isinstance(row, dict)
    }
    if not targets:
        return

    du.print_subheader("Target Surfaces")
    for surface_name, label in (
        ("family_id", "Family Target"),
        ("type_slug", "Type Target"),
        ("family_within_type", "Family Within Type"),
        ("category_primary", "Raw Primary Label"),
        ("category_subtype", "Raw Subtype Label"),
    ):
        row = targets.get(surface_name)
        if not isinstance(row, dict):
            continue
        value = (
            f"rows={int(row.get('present_rows', 0)):,} | "
            f"classes={int(row.get('unique_classes', 0)):,}"
        )
        if configured_min_support is not None:
            value += (
                f" | trainable@{int(row.get('min_support', configured_min_support))}="
                f"{int(row.get('trainable_classes_at_min_support', 0)):,}"
            )
        du.print_stat(label, value)

    support_rows = [
        row
        for row in summary.get("support_diagnostics", [])
        if isinstance(row, dict)
    ]
    benchmark_policy = (
        summary.get("benchmark_support_policy")
        if isinstance(summary.get("benchmark_support_policy"), dict)
        else {}
    )
    if support_rows:
        du.print_subheader("Support Diagnostics")
        for floor in SUPPORT_DIAGNOSTIC_FLOORS:
            row = next((item for item in support_rows if int(item.get("support_floor", 0)) == int(floor)), None)
            if not isinstance(row, dict):
                continue
            du.print_stat(
                f"trainable@{int(floor)}",
                (
                    f"family_classes={int(row.get('family_target_family_count', 0)):,} | "
                    f"type_classes={int(row.get('type_target_class_count', 0)):,}"
                ),
            )

    alignment = summary.get("alignment", {})
    if isinstance(alignment, dict) and int(alignment.get("rows_with_authoritative_type", 0)) > 0:
        du.print_stat(
            "Raw→Type Alignment",
            (
                f"subtype exact={float(alignment.get('subtype_exact_type_match_pct', 0.0)):.2f}% | "
                f"primary exact={float(alignment.get('primary_exact_type_match_pct', 0.0)):.2f}% | "
                f"inferred match={float(alignment.get('inferred_type_match_pct', 0.0)):.2f}%"
            ),
        )
    tier_counts = summary.get("tier_counts", {})
    if isinstance(tier_counts, dict) and tier_counts:
        du.print_stat(
            "Family Tiers",
            (
                f"major={int(tier_counts.get('major_family_samples', 0)):,} | "
                f"minor={int(tier_counts.get('minor_family_samples', 0)):,} | "
                f"generic/coarse={int(tier_counts.get('generic_coarse_label_samples', 0)):,} | "
                f"unresolved={int(tier_counts.get('unresolved_samples', 0)):,}"
            ),
        )
        if benchmark_policy.get("benchmark_min_support") not in (None, ""):
            du.print_stat(
                "Benchmark Eligibility",
                (
                    f"authority={int(tier_counts.get('authority_eligible_samples', 0)):,} | "
                    f"benchmark@{int(benchmark_policy.get('benchmark_min_support', 0))}="
                    f"{int(tier_counts.get('benchmark_eligible_samples', 0)):,} | "
                    f"support-excluded={int(tier_counts.get('excluded_below_benchmark_support_samples', 0)):,} | "
                    f"non-family-target={int(tier_counts.get('excluded_non_family_target_samples', 0)):,}"
                ),
            )


def _print_catalog_semantics(samples_df: pd.DataFrame) -> None:
    """Print additive Erebus catalog-semantics signals when present."""
    has_semantics = any(
        col in samples_df.columns
        for col in (
            "analysis_lane",
            "sample_label_kind",
            "payload_target_platform",
            "payload_target_source",
        )
    )
    if not has_semantics:
        return

    du.print_subheader("Catalog Semantics")
    if "analysis_lane" in samples_df.columns:
        lane_counts = samples_df["analysis_lane"].fillna("unknown").astype(str).value_counts()
        if len(lane_counts):
            top_lane = str(lane_counts.index[0])
            top_lane_count = int(lane_counts.iloc[0])
            du.print_stat("Top Analysis Lane", f"{top_lane} ({top_lane_count:,})")
        non_android = int(
            (
                samples_df["analysis_lane"].fillna("").astype(str).str.strip().str.lower()
                != "android_artifact"
            ).sum()
        )
        du.print_stat("Non-Android Lane Rows", non_android)

    if "sample_label_kind" in samples_df.columns:
        label_counts = samples_df["sample_label_kind"].fillna("unknown").astype(str).value_counts()
        if len(label_counts):
            top_kind = str(label_counts.index[0])
            top_kind_count = int(label_counts.iloc[0])
            du.print_stat("Top Sample Label Kind", f"{top_kind} ({top_kind_count:,})")
        label_kind_norm = (
            samples_df["sample_label_kind"].fillna("").astype(str).str.strip().str.lower()
        )
        du.print_stat("Filename Sample Labels", int((label_kind_norm == "filename").sum()))
        du.print_stat("Hash-like Sample Labels", int((label_kind_norm == "hash_like").sum()))
        du.print_stat("Opaque Sample Labels", int((label_kind_norm == "opaque_string").sum()))
        du.print_stat("UNCLASSIFIED Sample Labels", int((label_kind_norm == "unclassified").sum()))

    if "payload_target_platform" in samples_df.columns:
        target_counts = (
            samples_df["payload_target_platform"].fillna("unknown").astype(str).value_counts()
        )
        if len(target_counts):
            top_target = str(target_counts.index[0])
            top_target_count = int(target_counts.iloc[0])
            du.print_stat("Top Payload Target", f"{top_target} ({top_target_count:,})")
        target_norm = (
            samples_df["payload_target_platform"].fillna("").astype(str).str.strip().str.lower()
        )
        du.print_stat(
            "Non-Android Target Rows",
            int(((target_norm != "") & (target_norm != "android")).sum()),
        )

    if "payload_target_source" in samples_df.columns:
        source_counts = (
            samples_df["payload_target_source"].fillna("unknown").astype(str).value_counts()
        )
        if len(source_counts):
            top_source = str(source_counts.index[0])
            top_source_count = int(source_counts.iloc[0])
            du.print_stat("Top Payload Target Source", f"{top_source} ({top_source_count:,})")

    if "vt_family_token" in samples_df.columns:
        token_norm = samples_df["vt_family_token"].fillna("").astype(str).str.strip()
        du.print_stat("Rows With VT Family Token", int((token_norm != "").sum()))
        if "family_label_raw" in samples_df.columns:
            family_raw = (
                samples_df["family_label_raw"].fillna("").astype(str).str.strip().str.lower()
            )
            du.print_stat(
                "Blank Family Raw + VT Token",
                int(
                    (
                        (token_norm != "")
                        & family_raw.isin({"", "unknown", "generic", "unclassified", "unlabeled"})
                    ).sum()
                ),
            )
    if "sample_label_kind" in samples_df.columns and "family_canonical" in samples_df.columns:
        label_kind_norm = (
            samples_df["sample_label_kind"].fillna("").astype(str).str.strip().str.lower()
        )
        family_canonical = (
            samples_df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
        )
        du.print_stat(
            "Weak Labels With Canonical Family",
            int(
                (
                    label_kind_norm.isin({"filename", "hash_like", "opaque_string", "unclassified"})
                    & ~family_canonical.isin({"", "unknown", "other", "unmapped", "none", "null"})
                ).sum()
            ),
        )
    if "family_label_raw" in samples_df.columns and "family_canonical" in samples_df.columns:
        family_raw = (
            samples_df["family_label_raw"].fillna("").astype(str).str.strip().str.lower()
        )
        family_canonical = (
            samples_df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
        )
        du.print_stat(
            "Raw-vs-Canonical Family Conflicts",
            int(
                (
                    ~family_raw.isin({"", "unknown", "generic", "unclassified", "unlabeled"})
                    & ~family_canonical.isin({"", "unknown", "other", "unmapped", "none", "null"})
                    & (family_raw != family_canonical)
                ).sum()
            ),
        )

    if "source_batch_label" in samples_df.columns:
        batch_counts = samples_df["source_batch_label"].fillna("").astype(str).str.strip().value_counts()
        if len(batch_counts):
            top_batch = str(batch_counts.index[0] or "<blank>")
            top_batch_count = int(batch_counts.iloc[0])
            du.print_stat("Top Source Batch Label", f"{top_batch} ({top_batch_count:,})")
    _print_top_drift_groups(samples_df)
    _print_sql_scope_catalog_semantics_preview(samples_df)


def _print_sql_scope_catalog_semantics_preview(samples_df: pd.DataFrame) -> None:
    """Show SQL-scope semantics so upstream drift is visible before Python cleanup."""
    if not hasattr(samples_df, "attrs") or not isinstance(samples_df.attrs, dict):
        return
    sql_scope = samples_df.attrs.get("catalog_semantics_sql_scope")
    if not isinstance(sql_scope, dict) or not sql_scope:
        return
    scope_name = str(sql_scope.get("scope", "") or "").strip().lower()
    if scope_name == "sql_limited_loader_slice":
        header = "Loader Slice Catalog Preview"
        prefix = "Loader"
    else:
        header = "SQL Scope Catalog Preview"
        prefix = "SQL"

    lane_dist = sql_scope.get("analysis_lane_distribution") or {}
    label_dist = sql_scope.get("sample_label_kind_distribution") or {}
    target_dist = sql_scope.get("payload_target_platform_distribution") or {}
    batch_dist = sql_scope.get("source_batch_label_distribution") or {}

    du.print_subheader(header)
    if isinstance(lane_dist, dict) and lane_dist:
        top_lane, top_lane_count = next(iter(lane_dist.items()))
        du.print_stat(f"{prefix} Top Analysis Lane", f"{top_lane} ({int(top_lane_count):,})")
    if isinstance(label_dist, dict) and label_dist:
        top_kind, top_kind_count = next(iter(label_dist.items()))
        du.print_stat(f"{prefix} Top Sample Label Kind", f"{top_kind} ({int(top_kind_count):,})")
    if isinstance(target_dist, dict) and target_dist:
        top_target, top_target_count = next(iter(target_dist.items()))
        du.print_stat(f"{prefix} Top Payload Target", f"{top_target} ({int(top_target_count):,})")
    if isinstance(batch_dist, dict) and batch_dist:
        top_batch, top_batch_count = next(iter(batch_dist.items()))
        du.print_stat(f"{prefix} Top Source Batch Label", f"{top_batch} ({int(top_batch_count):,})")

    du.print_stat(f"{prefix} Non-Android Lane Rows", int(sql_scope.get("non_android_lane_rows", 0)))
    du.print_stat(
        f"{prefix} Non-Android Target Rows",
        int(sql_scope.get("non_android_payload_target_rows", 0)),
    )
    du.print_stat(f"{prefix} Filename Sample Labels", int(sql_scope.get("filename_label_rows", 0)))
    du.print_stat(f"{prefix} Hash-like Sample Labels", int(sql_scope.get("hash_like_label_rows", 0)))
    du.print_stat(f"{prefix} Opaque Sample Labels", int(sql_scope.get("opaque_label_rows", 0)))
    du.print_stat(f"{prefix} UNCLASSIFIED Sample Labels", int(sql_scope.get("unclassified_label_rows", 0)))
    du.print_stat(f"{prefix} Rows With VT Family Token", int(sql_scope.get("vt_family_token_rows", 0)))
    du.print_stat(
        f"{prefix} Blank Family Raw + VT Token",
        int(sql_scope.get("blank_family_raw_with_vt_token_rows", 0)),
    )
    du.print_stat(
        f"{prefix} Weak Labels With Canonical Family",
        int(sql_scope.get("weak_label_with_canonical_family_rows", 0)),
    )
    du.print_stat(
        f"{prefix} Raw-vs-Canonical Family Conflicts",
        int(sql_scope.get("raw_family_vs_canonical_conflict_rows", 0)),
    )


def _print_top_drift_groups(samples_df: pd.DataFrame) -> None:
    """Show the worst Android drift cohorts by family/type/source batch."""
    drift_groups = _collect_top_drift_groups(samples_df)
    if not drift_groups:
        return
    du.print_subheader("Top Drift Cohorts")
    for idx, row in enumerate(drift_groups[:3], start=1):
        summary = (
            f"{row['label']}: {row['group_value']} rows={int(row['rows'])}, "
            f"issues={int(row['issue_events'])}, dominant={row['dominant_issue']}:{int(row['dominant_count'])}, "
            f"weak={int(row['weak_label_rows'])}, conflicts={int(row['family_conflict_rows'])}"
        )
        du.print_stat(f"Drift Group {idx}", summary)


def _collect_top_drift_groups(samples_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Return the worst Android drift cohorts by family/type/source batch."""
    if samples_df.empty:
        return []

    frame = samples_df.copy()
    for col in ("family_canonical", "type_slug", "source_batch_label"):
        if col in frame.columns:
            frame[col] = frame[col].fillna("").astype(str).str.strip().replace("", "<blank>")
    lane = (
        frame["analysis_lane"].fillna("").astype(str).str.strip().str.lower()
        if "analysis_lane" in frame.columns
        else pd.Series([""] * len(frame), index=frame.index, dtype="object")
    )
    target = (
        frame["payload_target_platform"].fillna("").astype(str).str.strip().str.lower()
        if "payload_target_platform" in frame.columns
        else pd.Series([""] * len(frame), index=frame.index, dtype="object")
    )
    label_kind = (
        frame["sample_label_kind"].fillna("").astype(str).str.strip().str.lower()
        if "sample_label_kind" in frame.columns
        else pd.Series([""] * len(frame), index=frame.index, dtype="object")
    )
    vt_token = (
        frame["vt_family_token"].fillna("").astype(str).str.strip()
        if "vt_family_token" in frame.columns
        else pd.Series([""] * len(frame), index=frame.index, dtype="object")
    )
    family_raw = (
        frame["family_label_raw"].fillna("").astype(str).str.strip().str.lower()
        if "family_label_raw" in frame.columns
        else pd.Series([""] * len(frame), index=frame.index, dtype="object")
    )
    family_canonical = (
        frame["family_canonical"].fillna("").astype(str).str.strip().str.lower()
        if "family_canonical" in frame.columns
        else pd.Series([""] * len(frame), index=frame.index, dtype="object")
    )

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
    issue_frame = frame[frame["issue_rows"]].copy()
    if issue_frame.empty:
        return []
    group_specs = []
    if "family_canonical" in issue_frame.columns:
        group_specs.append(("families", "family_canonical"))
    if "type_slug" in issue_frame.columns:
        group_specs.append(("types", "type_slug"))
    if "source_batch_label" in issue_frame.columns:
        group_specs.append(("source batches", "source_batch_label"))

    def _normalize_sample_ids(value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, str):
            token = value.strip()
            return {token} if token else set()
        if isinstance(value, (tuple, list, set, frozenset)):
            return {str(v).strip() for v in value if str(v).strip()}
        to_list = getattr(value, "tolist", None)
        if callable(to_list):
            try:
                return {str(v).strip() for v in to_list() if str(v).strip()}
            except Exception:
                pass
        token = str(value).strip()
        return {token} if token else set()

    compact_candidates: list[dict[str, Any]] = []
    for label, group_col in group_specs:
        agg_spec: dict[str, tuple[str, str]] = {
            "rows": ("issue_rows", "size"),
            "non_android_lane_rows": ("issue_non_android_lane", "sum"),
            "non_android_target_rows": ("issue_non_android_target", "sum"),
            "weak_label_rows": ("issue_weak_label", "sum"),
            "blank_family_with_token_rows": ("issue_blank_family_with_token", "sum"),
            "family_conflict_rows": ("issue_family_conflict", "sum"),
        }
        if "sample_id" in issue_frame.columns:
            agg_spec["sample_ids"] = ("sample_id", lambda s: tuple(sorted({str(v).strip() for v in s.tolist() if str(v).strip()})))
        grouped = issue_frame.groupby(group_col, dropna=False).agg(**agg_spec).reset_index()
        grouped["issue_events"] = (
            grouped["non_android_lane_rows"]
            + grouped["non_android_target_rows"]
            + grouped["weak_label_rows"]
            + grouped["blank_family_with_token_rows"]
            + grouped["family_conflict_rows"]
        )
        grouped = grouped.sort_values(
            by=["issue_events", "rows"],
            ascending=[False, False],
            kind="stable",
        ).head(3)
        if grouped.empty:
            continue
        for _, top in grouped.iterrows():
            issue_buckets = {
                "weak_label": int(top["weak_label_rows"]),
                "family_conflict": int(top["family_conflict_rows"]),
                "blank_family_with_token": int(top["blank_family_with_token_rows"]),
                "non_android_lane": int(top["non_android_lane_rows"]),
                "non_android_target": int(top["non_android_target_rows"]),
            }
            dominant_issue, dominant_count = max(
                issue_buckets.items(),
                key=lambda item: (item[1], item[0]),
            )
            compact_candidates.append(
                {
                    "label": label,
                    "group_value": str(top[group_col]),
                    "rows": int(top["rows"]),
                    "issue_events": int(top["issue_events"]),
                    "weak_label_rows": int(top["weak_label_rows"]),
                    "family_conflict_rows": int(top["family_conflict_rows"]),
                    "dominant_issue": dominant_issue,
                    "dominant_count": int(dominant_count),
                    "sample_ids": _normalize_sample_ids(top["sample_ids"]) if "sample_ids" in top else set(),
                }
            )
    if not compact_candidates:
        return []
    compact_candidates.sort(
        key=lambda row: (
            -int(row["issue_events"]),
            -int(row["rows"]),
            str(row["label"]),
            str(row["group_value"]),
        )
    )
    selected: list[dict[str, Any]] = []
    for candidate in compact_candidates:
        candidate_ids = candidate.get("sample_ids") or set()
        if (
            str(candidate.get("label")) == "source batches"
            and str(candidate.get("group_value")) == "<blank>"
            and candidate_ids
        ):
            covered_by_specific_child = False
            for other in compact_candidates:
                if other is candidate:
                    continue
                if str(other.get("label")) == "source batches":
                    continue
                other_ids = other.get("sample_ids") or set()
                if not other_ids or not other_ids.issubset(candidate_ids):
                    continue
                if float(len(other_ids)) / float(len(candidate_ids)) >= 0.50:
                    covered_by_specific_child = True
                    break
            if covered_by_specific_child:
                continue
        duplicate = False
        for prior in selected:
            prior_ids = prior.get("sample_ids") or set()
            if candidate_ids and prior_ids:
                union = candidate_ids | prior_ids
                if union:
                    jaccard = float(len(candidate_ids & prior_ids)) / float(len(union))
                    if jaccard >= 0.95:
                        duplicate = True
                        break
        if duplicate:
            continue
        selected.append(candidate)
        if len(selected) >= 3:
            break
    return selected


def _print_cohort_policy(samples_df: pd.DataFrame, gates: dict) -> None:
    """Print active cohort policy knobs for reproducibility readability."""
    requested_excluded = samples_df.attrs.get("requested_exclude_families", ())
    sql_applied_excluded = samples_df.attrs.get("sql_exclude_families_applied", ())
    exclude_deferred = bool(samples_df.attrs.get("exclude_families_deferred_by_snapshot_lock", False))
    configured_min_support = samples_df.attrs.get(
        "configured_min_samples_per_family",
        resolve_configured_min_samples_per_family(gates),
    )
    diagnostic_min_support = int(
        samples_df.attrs.get(
            "diagnostic_min_samples_per_family",
            resolve_diagnostic_min_samples_per_family(gates),
        )
    )
    support_floor_mode = str(
        samples_df.attrs.get("support_floor_mode", resolve_support_floor_mode(gates)) or ""
    ).strip().lower()
    min_support_applied_in_sql = bool(samples_df.attrs.get("min_samples_per_family_applied_in_sql", True))
    min_support_sql_value = samples_df.attrs.get("min_samples_per_family_sql_value")
    exclude_unknown = bool(gates.get("exclude_unknown_type_slug", False))
    du.print_subheader("Cohort Policy")
    excluded_display = requested_excluded if requested_excluded else sql_applied_excluded
    excluded_txt = ", ".join([str(x) for x in excluded_display]) if excluded_display else "(none)"
    if exclude_deferred and excluded_display:
        excluded_txt = f"{excluded_txt} (deferred by snapshot lock)"
    du.print_stat("Excluded Families", excluded_txt)
    du.print_stat("Excluded Types", "unknown" if exclude_unknown else "(none)")
    if configured_min_support in (None, ""):
        min_support_txt = f"diagnostic only (no admission gate; trainability shown at 20/10/5/3/1, runtime={diagnostic_min_support})"
    elif support_floor_mode == "benchmark_eligibility":
        min_support_txt = (
            f"benchmark only (n>={int(configured_min_support)} for supervised family benchmarking; "
            "broad corpus, taxonomy, and permission diagnostics retain all rows)"
        )
    else:
        min_support_txt = str(int(configured_min_support))
        if not min_support_applied_in_sql:
            min_support_txt = f"{min_support_txt} (deferred by snapshot lock)"
        elif min_support_sql_value not in (None, "") and int(min_support_sql_value) != int(configured_min_support):
            min_support_txt = f"{int(configured_min_support)} (SQL applied {int(min_support_sql_value)})"
    if support_floor_mode == "diagnostic_only" and configured_min_support not in (None, ""):
        min_support_txt += f" [{support_floor_mode}]"
    du.print_stat("Minimum Family Support", min_support_txt)


def _print_cohort_verdict(
    *,
    total: int,
    missing_pkg: float,
    max_missing_pkg_pct: float,
    fam_col: str | None,
    samples_df: pd.DataFrame,
) -> list[str]:
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

    warning_messages: list[str] = []
    if missing_pkg > max_missing_pkg_pct:
        warning_messages.append(
            f"missing package name {missing_pkg:.2f}% exceeds threshold {max_missing_pkg_pct:.2f}%"
        )
    if top_family_share >= 0.30:
        warning_messages.append(
            f"top family concentration {top_family_share * 100.0:.2f}% exceeds 30.00%"
        )
    if banker_share >= 0.60:
        warning_messages.append(
            f"banker share {banker_share * 100.0:.2f}% exceeds 60.00%"
        )
    gate_stats = {}
    if hasattr(samples_df, "attrs") and isinstance(samples_df.attrs, dict):
        raw_stats = samples_df.attrs.get("cohort_gate_stats")
        if isinstance(raw_stats, dict):
            gate_stats = raw_stats
    sql_scope_total = int(gate_stats.get("total_candidates") or 0)
    governed_ref = int(gate_stats.get("governed_cohort_count") or gate_stats.get("final_count_estimate") or 0)
    if sql_scope_total > 0:
        prepared_pct = float(total) / float(sql_scope_total)
        if prepared_pct < 0.60:
            warning_messages.append(
                f"prepared cohort retains only {prepared_pct * 100.0:.2f}% of SQL profile scope"
            )
    if sql_scope_total > 0 and governed_ref > 0:
        governed_pct = float(governed_ref) / float(sql_scope_total)
        if governed_pct < 0.85:
            warning_messages.append(
                f"SQL governed cohort retains only {governed_pct * 100.0:.2f}% of SQL profile scope"
            )
    sql_scope_semantics = (
        samples_df.attrs.get("catalog_semantics_sql_scope", {})
        if hasattr(samples_df, "attrs") and isinstance(samples_df.attrs, dict)
        else {}
    )
    if isinstance(sql_scope_semantics, dict) and sql_scope_semantics:
        sql_non_android_lane_rows = int(sql_scope_semantics.get("non_android_lane_rows", 0))
        prepared_non_android_lane_rows = 0
        if "analysis_lane" in samples_df.columns:
            lane_norm = samples_df["analysis_lane"].fillna("").astype(str).str.strip().str.lower()
            prepared_non_android_lane_rows = int((lane_norm != "android_artifact").sum())
        if sql_non_android_lane_rows > prepared_non_android_lane_rows:
            warning_messages.append(
                "SQL scope contains more non-android analysis_lane drift than the prepared cohort "
                f"({sql_non_android_lane_rows} vs {prepared_non_android_lane_rows})"
            )
        sql_weak_labels = int(sql_scope_semantics.get("weak_label_with_canonical_family_rows", 0))
        prepared_weak_labels = 0
        if "sample_label_kind" in samples_df.columns and "family_canonical" in samples_df.columns:
            label_kind_norm = (
                samples_df["sample_label_kind"].fillna("").astype(str).str.strip().str.lower()
            )
            family_canonical = (
                samples_df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
            )
            prepared_weak_labels = int(
                (
                    label_kind_norm.isin({"filename", "hash_like", "opaque_string", "unclassified"})
                    & ~family_canonical.isin({"", "unknown", "other", "unmapped", "none", "null"})
                ).sum()
            )
        if sql_weak_labels > prepared_weak_labels:
            warning_messages.append(
                "SQL scope contains more weak-label rows with canonical family authority than the "
                f"prepared cohort ({sql_weak_labels} vs {prepared_weak_labels})"
            )
    if "analysis_lane" in samples_df.columns:
        lane_norm = samples_df["analysis_lane"].fillna("").astype(str).str.strip().str.lower()
        non_android_lane_rows = int((lane_norm != "android_artifact").sum())
        if non_android_lane_rows > 0:
            warning_messages.append(
                f"non-android analysis_lane rows present: {non_android_lane_rows}"
            )
    if "payload_target_platform" in samples_df.columns:
        target_norm = (
            samples_df["payload_target_platform"].fillna("").astype(str).str.strip().str.lower()
        )
        non_android_target_rows = int(((target_norm != "") & (target_norm != "android")).sum())
        if non_android_target_rows > 0:
            warning_messages.append(
                f"non-android payload_target_platform rows present: {non_android_target_rows}"
            )
    if "sample_label_kind" in samples_df.columns:
        label_kind_norm = (
            samples_df["sample_label_kind"].fillna("").astype(str).str.strip().str.lower()
        )
        hash_like_rows = int((label_kind_norm == "hash_like").sum())
        opaque_rows = int((label_kind_norm == "opaque_string").sum())
        unclassified_rows = int((label_kind_norm == "unclassified").sum())
        if hash_like_rows > 0:
            warning_messages.append(f"hash-like sample labels remain: {hash_like_rows}")
        if opaque_rows > 0:
            warning_messages.append(f"opaque sample labels remain: {opaque_rows}")
        if unclassified_rows > 0:
            warning_messages.append(f"UNCLASSIFIED sample labels remain: {unclassified_rows}")
    if "vt_family_token" in samples_df.columns and "family_label_raw" in samples_df.columns:
        token_norm = samples_df["vt_family_token"].fillna("").astype(str).str.strip()
        family_raw = (
            samples_df["family_label_raw"].fillna("").astype(str).str.strip().str.lower()
        )
        blank_family_with_token = int(
            (
                (token_norm != "")
                & family_raw.isin({"", "unknown", "generic", "unclassified", "unlabeled"})
            ).sum()
        )
        if blank_family_with_token > 0:
            warning_messages.append(
                f"blank/generic family_label_raw despite vt_family_token: {blank_family_with_token}"
            )
    if "sample_label_kind" in samples_df.columns and "family_canonical" in samples_df.columns:
        label_kind_norm = (
            samples_df["sample_label_kind"].fillna("").astype(str).str.strip().str.lower()
        )
        family_canonical = (
            samples_df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
        )
        weak_label_with_authority = int(
            (
                label_kind_norm.isin({"filename", "hash_like", "opaque_string", "unclassified"})
                & ~family_canonical.isin({"", "unknown", "other", "unmapped", "none", "null"})
            ).sum()
        )
        if weak_label_with_authority > 0:
            warning_messages.append(
                f"weak sample labels despite canonical family authority: {weak_label_with_authority}"
            )
    if "family_label_raw" in samples_df.columns and "family_canonical" in samples_df.columns:
        family_raw = (
            samples_df["family_label_raw"].fillna("").astype(str).str.strip().str.lower()
        )
        family_canonical = (
            samples_df["family_canonical"].fillna("").astype(str).str.strip().str.lower()
        )
        raw_vs_canonical_conflicts = int(
            (
                ~family_raw.isin({"", "unknown", "generic", "unclassified", "unlabeled"})
                & ~family_canonical.isin({"", "unknown", "other", "unmapped", "none", "null"})
                & (family_raw != family_canonical)
            ).sum()
        )
        if raw_vs_canonical_conflicts > 0:
            warning_messages.append(
                f"raw family label differs from canonical family: {raw_vs_canonical_conflicts}"
            )
    warn = bool(warning_messages)
    if warn:
        du.print_warning(
            "[COHORT] Cohort is usable but remains concentration-heavy and/or has notable missingness."
        )
    else:
        du.print_info("[COHORT] Filtered multi-type malware cohort ready for downstream analysis.")
    return warning_messages
