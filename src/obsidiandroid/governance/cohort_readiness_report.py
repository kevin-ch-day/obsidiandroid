"""Readiness summaries and SQL-scope gate diagnostics for training cohorts.

Operator vocabulary (see ``obsidiandroid.diagnostics.cohort_vocabulary``):

* **SQL profile scope** — database head count before rows are materialized into ``samples_df``.
* **Prepared cohort** — rows in ``samples_df`` after fetch + Python preparation.
"""

from __future__ import annotations

import pandas as pd
from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console
from obsidiandroid.diagnostics import taxonomy_target_surface_report


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
    fam_col = _family_column(samples_df)

    du.print_section("Cohort Readiness Summary")
    du.print_stat("Final Samples", f"{total:,}")
    sql_scope_total = int(gate_stats.get("total_candidates") or 0)
    governed_ref = int(gate_stats.get("governed_cohort_count") or gate_stats.get("final_count_estimate") or 0)
    if sql_scope_total > 0:
        du.print_stat("SQL Profile Scope", f"{sql_scope_total:,}")
    if governed_ref > 0 and governed_ref != total:
        du.print_stat("SQL governed cohort (reference)", f"{governed_ref:,}")
        pct = round(100.0 * float(total) / float(governed_ref), 2)
        du.print_note(
            f"Prepared cohort is {total:,} rows ({pct}% of the SQL-governed reference). "
            "The difference is from Python-side preparation after the fetch "
            "(profile dataset_filters, malware/cohort labeling, contract gates, snapshot locks)."
        )
    if sql_scope_total > 0:
        du.print_subheader("Cohort Attrition")
        if governed_ref > 0:
            governed_pct = round(100.0 * float(governed_ref) / float(sql_scope_total), 2)
            du.print_stat(
                "SQL Scope → Governed",
                f"{governed_ref:,}/{sql_scope_total:,} ({governed_pct:.2f}%)",
            )
        prepared_pct = round(100.0 * float(total) / float(sql_scope_total), 2)
        du.print_stat(
            "SQL Scope → Prepared",
            f"{total:,}/{sql_scope_total:,} ({prepared_pct:.2f}%)",
        )
    du.print_stat("Unique Families", _unique_count(samples_df, fam_col))
    du.print_stat("Represented Types", _unique_count(samples_df, "type_slug"))
    _print_taxonomy_target_surfaces(samples_df, gates=gates)

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
        max_type_rows = 3 if ml_console.is_compact() else len(counts)
        for key, value in counts.head(max_type_rows).items():
            pct = (float(value) / max(total, 1)) * 100.0
            du.print_info(f"  - {key}: {value:,} ({pct:.2f}%)")
        if len(counts) > max_type_rows:
            du.print_info(
                f"  - ... {len(counts) - max_type_rows} additional type bucket(s) in diagnostics / dataframe exports."
            )

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

        top_family_limit = 5 if ml_console.is_compact() else 10
        du.print_subheader(f"Top Families (Top {top_family_limit})")
        for key, value in fam_counts.head(top_family_limit).items():
            du.print_info(f"  - {key}: {int(value):,}")
        if len(fam_counts) > top_family_limit:
            du.print_info(
                f"  - ... {len(fam_counts) - top_family_limit} additional families omitted from terminal output."
            )

    _print_catalog_semantics(samples_df)
    _print_cohort_policy(samples_df=samples_df, gates=gates)
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
        low_support_txt = "(deferred by snapshot lock)"
    else:
        low_support_txt = str(int(stats.get("excluded_low_support", 0)))
    du.print_stat("Excluded Low Support", low_support_txt)
    governed = int(stats.get("governed_cohort_count", stats.get("final_count_estimate", 0)))
    du.print_stat("Governed row count from SQL (authoritative)", governed)
    legacy = stats.get("final_count_estimate_sequential_legacy")
    if legacy is not None and int(legacy) != governed:
        du.print_info(
            f"[COHORT] Sequential marginal estimate was {int(legacy)} "
            f"(overlapping exclusion buckets — use governed SQL count above)."
        )


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
    try:
        min_support = int(gates.get("min_samples_per_family", 3))
    except (TypeError, ValueError):
        min_support = 3
    summary = taxonomy_target_surface_report.build_taxonomy_target_surface_summary(
        samples_df,
        min_support=min_support,
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
        du.print_stat(
            label,
            (
                f"rows={int(row.get('present_rows', 0)):,} | "
                f"classes={int(row.get('unique_classes', 0)):,} | "
                f"trainable@{int(row.get('min_support', min_support))}="
                f"{int(row.get('trainable_classes_at_min_support', 0)):,}"
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
    if samples_df.empty:
        return

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
        return

    du.print_subheader("Top Drift Cohorts")
    group_specs = []
    if "family_canonical" in issue_frame.columns:
        group_specs.append(("families", "family_canonical"))
    if "type_slug" in issue_frame.columns:
        group_specs.append(("types", "type_slug"))
    if "source_batch_label" in issue_frame.columns:
        group_specs.append(("source batches", "source_batch_label"))
    for label, group_col in group_specs:
        grouped = (
            issue_frame.groupby(group_col, dropna=False)
            .agg(
                rows=("issue_rows", "size"),
                non_android_lane_rows=("issue_non_android_lane", "sum"),
                non_android_target_rows=("issue_non_android_target", "sum"),
                weak_label_rows=("issue_weak_label", "sum"),
                blank_family_with_token_rows=("issue_blank_family_with_token", "sum"),
                family_conflict_rows=("issue_family_conflict", "sum"),
            )
            .reset_index()
        )
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
        du.print_info(f"  {label}:")
        for _, row in grouped.iterrows():
            du.print_info(
                "    - "
                f"{row[group_col]}: rows={int(row['rows'])}, "
                f"issue_events={int(row['issue_events'])}, "
                f"weak_label_rows={int(row['weak_label_rows'])}, "
                f"family_conflicts={int(row['family_conflict_rows'])}"
            )


def _print_cohort_policy(samples_df: pd.DataFrame, gates: dict) -> None:
    """Print active cohort policy knobs for reproducibility readability."""
    requested_excluded = samples_df.attrs.get("requested_exclude_families", ())
    sql_applied_excluded = samples_df.attrs.get("sql_exclude_families_applied", ())
    exclude_deferred = bool(samples_df.attrs.get("exclude_families_deferred_by_snapshot_lock", False))
    configured_min_support = int(
        samples_df.attrs.get(
            "configured_min_samples_per_family",
            gates.get(
                "min_samples_per_family",
                getattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", getattr(app_config, "MIN_FAMILY_SUPPORT", 3)),
            ),
        )
        or 3
    )
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
    min_support_txt = str(configured_min_support)
    if not min_support_applied_in_sql:
        min_support_txt = f"{min_support_txt} (deferred by snapshot lock)"
    elif min_support_sql_value not in (None, "") and int(min_support_sql_value) != configured_min_support:
        min_support_txt = f"{configured_min_support} (SQL applied {int(min_support_sql_value)})"
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
