"""Non-plot bundle exports for permission-trends reporting.

This module holds small writers that emit CSV/MD/TXT artifacts into the
permission-trends bundle directory structure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config

from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.pipeline.permission_trends.bundle_io import (
    export_df_with_latest,
    export_markdown_with_latest,
    export_text_with_latest,
)
from obsidiandroid.pipeline.permission_trends.constants import (
    ARTIFACT_GROUP_CONTRACTS,
    ARTIFACT_GROUP_DOCS,
    ARTIFACT_GROUP_FIGURES,
    ARTIFACT_GROUP_TABLES,
    PERMISSION_ALIAS_MAP,
    RUN_SUFFIX_PNG_PATTERN,
)


def build_permission_trends_layout_check(*, bundle_dir: Path) -> dict[str, Any]:
    """Validate latest permission bundle taxonomy and retention policy."""
    group_names = {
        ARTIFACT_GROUP_FIGURES,
        ARTIFACT_GROUP_TABLES,
        ARTIFACT_GROUP_CONTRACTS,
        ARTIFACT_GROUP_DOCS,
    }
    allowed_ext = {
        ARTIFACT_GROUP_FIGURES: {".png"},
        ARTIFACT_GROUP_TABLES: {".csv"},
        ARTIFACT_GROUP_CONTRACTS: {".json", ".csv"},
        ARTIFACT_GROUP_DOCS: {".md", ".txt"},
    }
    checks: dict[str, Any] = {
        "bundle_dir": str(bundle_dir),
        "group_counts": {},
        "unexpected_group_files": [],
        "disallowed_extensions": [],
        "timestamped_png_in_latest_count": 0,
        "status": "PASS",
    }
    if not bundle_dir.exists():
        checks["status"] = "WARN"
        checks["unexpected_group_files"].append("bundle_dir_missing")
        return checks
    for path in bundle_dir.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(bundle_dir).parts
        group = rel_parts[0] if rel_parts else ""
        if group not in group_names:
            checks["unexpected_group_files"].append(str(path.relative_to(bundle_dir)))
            continue
        checks["group_counts"][group] = int(checks["group_counts"].get(group, 0)) + 1
        suffix = path.suffix.lower()
        if suffix not in allowed_ext[group]:
            checks["disallowed_extensions"].append(str(path.relative_to(bundle_dir)))
        if group == ARTIFACT_GROUP_FIGURES and RUN_SUFFIX_PNG_PATTERN.match(path.name):
            checks["timestamped_png_in_latest_count"] = int(checks["timestamped_png_in_latest_count"]) + 1
    if checks["unexpected_group_files"] or checks["disallowed_extensions"] or checks["timestamped_png_in_latest_count"]:
        checks["status"] = "WARN"
    return checks


def export_alias_map_csv(*, run_id: str, bundle_dir: Path) -> str:
    df = pd.DataFrame(
        [{"alias_from": key, "alias_to": value} for key, value in sorted(PERMISSION_ALIAS_MAP.items())]
    )
    return export_df_with_latest(
        df,
        run_id,
        "permission_alias_map",
        bundle_dir,
        artifact_group=ARTIFACT_GROUP_CONTRACTS,
    )


def export_safe_claims_report(
    *,
    run_id: str,
    bundle_dir: Path,
    coverage_df: pd.DataFrame,
    banker_enrichment_df: pd.DataFrame,
    dangerous_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    selected_vendor_count: int,
    select_banker_summary_rows: Any,
) -> str:
    lines = [f"Run ID: {run_id}", "", "Safe claims:"]
    if not coverage_df.empty:
        cov = coverage_df.iloc[0].to_dict()
        lines.append(
            f"- Permission rows coverage is {float(cov.get('pct_with_permission_rows', 0.0)):.3f} on snapshot."
        )
        lines.append(
            f"- Zero-permission share is {float(cov.get('pct_zero_permissions', 0.0)):.3f}; denominators include these samples."
        )
    if not banker_enrichment_df.empty:
        top = select_banker_summary_rows(banker_enrichment_df, limit=3)
        for _, row in top.iterrows():
            lines.append(
                f"- Banker enrichment shows {row['permission']} with OR={float(row['odds_ratio']):.3f} (FDR={float(row['p_value_fdr_bh']):.3e})."
            )
    if not dangerous_df.empty:
        max_unknown = float(dangerous_df["unknown_protection_rate"].max())
        lines.append(f"- Unknown protection-level rate is reported by type (max mean={max_unknown:.3f}).")
    if isinstance(consensus_df, pd.DataFrame) and not consensus_df.empty:
        excluded = int(pd.to_numeric(consensus_df["low_vendor_count_flag"], errors="coerce").fillna(0).sum())
        lines.append(f"- Consensus inferential analyses exclude {excluded} samples with vendor_count < 5.")

    lines.extend(["", "Unsafe claims:"])
    lines.append("- Do not claim causal links; all consensus/entropy relationships are associations.")
    lines.append("- Do not claim bankers are globally SMS-heavy; use subtype framing.")
    if selected_vendor_count < safe_int_config_value(
        getattr(app_config, "FEATURE_MIN_SELECTED_VENDORS", 1),
        default=1,
    ):
        lines.append("- This run is vendor-constrained; avoid broad ablation generalization.")
    lines.append("- Do not infer runtime behavior from static manifest permissions.")

    text = "\n".join(lines) + "\n"
    return export_text_with_latest(text, run_id, "safe_claims", bundle_dir)


def export_paper_figures_index(
    *,
    run_id: str,
    bundle_dir: Path,
    type_heatmap_png: str | None,
    banker_bar_png: str | None,
    generic_scatter_png: str | None,
    jsd_png: str | None,
    temporal_trends_png: str | None,
    banker_enrichment_csv: str,
) -> str:
    _ = banker_bar_png, generic_scatter_png, temporal_trends_png, banker_enrichment_csv
    lines = [
        f"# Paper Figures Index ({run_id})",
        "",
        "Recommended main figures:",
        f"1. Type permission heatmap: {type_heatmap_png or 'not generated'}",
        "2. Dangerous permission distribution by type: type_permission_heatmap_dangerous_only.latest.png",
        f"4. Family JSD heatmap (top families): {jsd_png or 'not generated'}",
        "5. Confusion matrix (random_forest): output/runs/<run_id>/conf_matrices/confusion_matrix_random_forest.png",
        "",
        "Recommended main tables:",
        "- cohort summary, temporal family scope, model comparison, ablation, dangerous stats tests",
    ]
    text = "\n".join(lines) + "\n"
    return export_markdown_with_latest(text, run_id, "paper_figures_index", bundle_dir)


def export_run_summary_onepager(
    *,
    run_id: str,
    profile_id: str,
    bundle_dir: Path,
    coverage_df: pd.DataFrame,
    dangerous_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    bundle_metadata: dict[str, Any],
    banker_enrichment_df: pd.DataFrame,
    select_banker_summary_rows: Any,
    discriminability_df: pd.DataFrame | None = None,
    type_entropy_df: pd.DataFrame | None = None,
    family_profiles_df: pd.DataFrame | None = None,
    type_capability_df: pd.DataFrame | None = None,
    family_capability_df: pd.DataFrame | None = None,
    attack_hypotheses_df: pd.DataFrame | None = None,
) -> str:
    coverage = coverage_df.iloc[0].to_dict() if not coverage_df.empty else {}
    unknown_rate = float(dangerous_df["unknown_protection_rate"].mean()) if not dangerous_df.empty else 0.0
    excluded = (
        int(pd.to_numeric(consensus_df.get("low_vendor_count_flag", 0), errors="coerce").fillna(0).sum())
        if isinstance(consensus_df, pd.DataFrame) and not consensus_df.empty
        else 0
    )
    top = (
        select_banker_summary_rows(banker_enrichment_df, limit=5)
        if not banker_enrichment_df.empty
        else pd.DataFrame()
    )
    lines = [
        f"# Run Summary ({run_id})",
        "",
        f"- Profile: {profile_id}",
        f"- Snapshot size: {int(coverage.get('sample_count', 0))}",
        f"- Permission coverage: {float(coverage.get('pct_with_permission_rows', 0.0)):.3f}",
        f"- Unknown protection rate (mean by type): {unknown_rate:.3f}",
        f"- vendor_constrained_run_flag: {bool(bundle_metadata.get('vendor_constrained_run_flag', False))}",
        f"- Consensus exclusions (vendor_count<5): {excluded}",
        "",
        "Dataset time contract:",
    ]
    contract = bundle_metadata.get("dataset_time_contract", {}) if isinstance(bundle_metadata, dict) else {}
    if isinstance(contract, dict) and contract:
        lines.extend(
            [
                f"- timestamp_field: {contract.get('timestamp_field', 'effective_first_seen_at_utc')}",
                f"- start_utc: {contract.get('start_utc')}",
                f"- end_utc: {contract.get('end_utc')}",
                f"- fallback_order: {contract.get('fallback_order')}",
            ]
        )
    else:
        lines.append("- dataset_time_contract: not available")
    lines.extend(
        [
            "",
            "Top banker enrichment (AOSP-only primary):",
        ]
    )
    if top.empty:
        lines.append("- No banker enrichment rows available.")
    else:
        for _, row in top.iterrows():
            lines.append(
                f"- {row['permission']}: OR={float(row['odds_ratio']):.3f}, FDR={float(row['p_value_fdr_bh']):.3e}"
            )

    if isinstance(discriminability_df, pd.DataFrame) and not discriminability_df.empty:
        top_disc = discriminability_df.head(5).copy()
        lines.extend(["", "Top permission discriminators:"])
        for _, row in top_disc.iterrows():
            lines.append(
                f"- {row['permission']}: Cramer's V={float(row['cramers_v']):.3f}, support={int(row['global_support'])}"
            )

    if isinstance(type_entropy_df, pd.DataFrame) and not type_entropy_df.empty:
        top_types = (
            type_entropy_df.sort_values(
                by=["sample_count", "permission_entropy", "type_slug"],
                ascending=[False, False, True],
                kind="mergesort",
            )
            .head(4)
            .copy()
        )
        lines.extend(["", "Type permission patterns:"])
        for _, row in top_types.iterrows():
            lines.append(
                f"- {row['type_slug']}: entropy={float(row['permission_entropy']):.3f}, "
                f"effective_diversity={float(row['effective_diversity']):.2f}, n={int(row['sample_count'])}"
            )
    if isinstance(type_capability_df, pd.DataFrame) and not type_capability_df.empty:
        cap_top = (
            type_capability_df.sort_values(
                by=["sample_count", "prevalence", "type_slug", "capability_bundle"],
                ascending=[False, False, True, True],
                kind="mergesort",
            )
            .groupby(["type_slug", "sample_count"], as_index=False, sort=False)
            .head(3)
        )
        lines.extend(["", "Type capability bundles:"])
        for type_slug, group in cap_top.groupby("type_slug", sort=False):
            sample_count = int(pd.to_numeric(group["sample_count"], errors="coerce").fillna(0).iloc[0])
            bundles = ", ".join(
                f"{row['capability_bundle']}={float(row['prevalence']):.2f} "
                f"({row.get('pattern_label', 'Weak Pattern')}, {row.get('pattern_confidence', 'low')})"
                for _, row in group.iterrows()
            )
            lines.append(f"- {type_slug} (n={sample_count}): {bundles}")

    if isinstance(family_profiles_df, pd.DataFrame) and not family_profiles_df.empty:
        family_scope_df = family_profiles_df.copy()
        if "profile_scope" in family_scope_df.columns:
            main_scope = family_scope_df[family_scope_df["profile_scope"].astype(str) == "main"].copy()
            if not main_scope.empty:
                family_scope_df = main_scope
        family_examples = (
            family_scope_df.sort_values(
                by=["sample_count", "family_canonical", "prevalence", "permission"],
                ascending=[False, True, False, True],
                kind="mergesort",
            )
            .groupby(["family_canonical", "sample_count"], as_index=False, sort=False)
            .head(3)
        )
        lines.extend(["", "Example family permission signatures:"])
        for family_name, group in family_examples.groupby("family_canonical", sort=False):
            sample_count = int(pd.to_numeric(group["sample_count"], errors="coerce").fillna(0).iloc[0])
            permissions = ", ".join(
                f"{str(row['permission']).replace('android.permission.', '')}={float(row['prevalence']):.2f} "
                f"({row.get('pattern_label', 'Weak Pattern')}, {row.get('pattern_confidence', 'low')})"
                for _, row in group.iterrows()
            )
            lines.append(f"- {family_name} (n={sample_count}): {permissions}")
    if isinstance(family_capability_df, pd.DataFrame) and not family_capability_df.empty:
        cap_examples = (
            family_capability_df.sort_values(
                by=["sample_count", "family_canonical", "prevalence", "capability_bundle"],
                ascending=[False, True, False, True],
                kind="mergesort",
            )
            .groupby(["family_canonical", "sample_count"], as_index=False, sort=False)
            .head(3)
        )
        lines.extend(["", "Example family capability bundles:"])
        for family_name, group in cap_examples.groupby("family_canonical", sort=False):
            sample_count = int(pd.to_numeric(group["sample_count"], errors="coerce").fillna(0).iloc[0])
            bundles = ", ".join(
                f"{row['capability_bundle']}={float(row['prevalence']):.2f} "
                f"({row.get('pattern_label', 'Weak Pattern')}, {row.get('pattern_confidence', 'low')})"
                for _, row in group.iterrows()
            )
            lines.append(f"- {family_name} (n={sample_count}): {bundles}")
    if isinstance(attack_hypotheses_df, pd.DataFrame) and not attack_hypotheses_df.empty:
        lines.extend(["", "Top ATT&CK-Mobile capability hypotheses:"])
        ordered = attack_hypotheses_df.sort_values(
            by=["group_kind", "sample_count", "matched_permission_count", "evidence_prevalence_mean"],
            ascending=[True, False, False, False],
            kind="mergesort",
        )
        for _, row in ordered.head(6).iterrows():
            lines.append(
                f"- {row['group_kind']} `{row['group_value']}` -> `{row['attack_id']}` {row['attack_name']} "
                f"[{row['confidence']}; {row.get('pattern_label', 'Weak Pattern')}, "
                f"{row.get('pattern_confidence', 'low')}] via {row['evidence_permissions']}"
            )
    text = "\n".join(lines) + "\n"
    return export_markdown_with_latest(text, run_id, "run_summary_onepager", bundle_dir)


def export_permission_pattern_summary(
    *,
    run_id: str,
    bundle_dir: Path,
    prevalence_by_type_df: pd.DataFrame,
    prevalence_by_family_df: pd.DataFrame,
    signal_prevalence_by_type_df: pd.DataFrame,
    signal_prevalence_by_type_behavior_safe_df: pd.DataFrame,
    signal_prevalence_by_family_df: pd.DataFrame,
    signal_prevalence_by_family_behavior_safe_df: pd.DataFrame,
    family_signal_similarity_df: pd.DataFrame,
    family_signal_similarity_behavior_safe_df: pd.DataFrame,
    signal_governance_coverage_df: pd.DataFrame,
    type_enrichment_df: pd.DataFrame,
    family_enrichment_df: pd.DataFrame,
    family_similarity_df: pd.DataFrame,
    attack_hypotheses_df: pd.DataFrame,
    generic_summary_df: pd.DataFrame,
    temporal_pattern_df: pd.DataFrame | None = None,
) -> str:
    broad_family_df = (
        prevalence_by_family_df.copy()
        if isinstance(prevalence_by_family_df, pd.DataFrame)
        else pd.DataFrame()
    )
    lines = [
        "# Permission Pattern Discovery Summary",
        "",
        f"Run ID: `{run_id}`",
        "",
        "Permissions are treated here as static declared-capability signals, not direct proof of runtime behavior or causality.",
        "",
        "## Broad corpus signal",
    ]
    if isinstance(prevalence_by_type_df, pd.DataFrame) and not prevalence_by_type_df.empty:
        common = (
            prevalence_by_type_df.groupby("permission", dropna=False)["permission_positive_count"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
        )
        lines.append("")
        lines.append("Top common permissions:")
        for permission, count in common.items():
            lines.append(f"- {permission}: positive_count={int(count)}")
    else:
        lines.append("")
        lines.append("No type-level prevalence rows available.")

    lines.extend(["", "## Type-level signal"])
    if isinstance(type_enrichment_df, pd.DataFrame) and not type_enrichment_df.empty:
        top_type = (
            type_enrichment_df[type_enrichment_df["interpretation_bucket"].astype(str) != "no_signal"]
            .sort_values(
                by=["q_value_fdr", "odds_ratio", "type_slug", "permission"],
                ascending=[True, False, True, True],
                kind="mergesort",
            )
            .head(10)
        )
        if top_type.empty:
            lines.append("")
            lines.append("No type-distinguishing permissions met the current significance/odds thresholds.")
        else:
            lines.append("")
            lines.append("Top type-distinguishing permissions:")
            for _, row in top_type.iterrows():
                lines.append(
                    f"- {row['type_slug']} :: {row['permission']}: "
                    f"OR={float(row['odds_ratio']):.2f}, q={float(row['q_value_fdr']):.3e}, "
                    f"bucket={row['interpretation_bucket']}, "
                    f"pattern={row.get('pattern_label', 'Weak Pattern')}"
                )
    else:
        lines.append("")
        lines.append("No type enrichment rows available.")

    lines.extend(["", "## Signal-group interpretation"])
    if isinstance(signal_prevalence_by_type_df, pd.DataFrame) and not signal_prevalence_by_type_df.empty:
        behavior_safe = signal_prevalence_by_type_behavior_safe_df.sort_values(
            by=["prevalence_pct", "type_slug", "signal_key"],
            ascending=[False, True, True],
            kind="mergesort",
        ).head(12)
        model_only = signal_prevalence_by_type_df[
            signal_prevalence_by_type_df["include_in_model_features"].astype(bool)
            & ~signal_prevalence_by_type_df["include_in_behavioral_claims"].astype(bool)
        ].sort_values(
            by=["prevalence_pct", "type_slug", "signal_key"],
            ascending=[False, True, True],
            kind="mergesort",
        ).head(12)
        lines.append("")
        lines.append("Behavior-claim-safe signal groups:")
        for _, row in behavior_safe.iterrows():
            lines.append(
                f"- {row['type_slug']} :: {row['signal_key']}: "
                f"prevalence={float(row['prevalence_pct']):.1f}%, "
                f"pattern={row.get('pattern_label', 'Weak Pattern')}"
            )
        lines.append("")
        lines.append("Model-only / fingerprint signal groups:")
        for _, row in model_only.iterrows():
            lines.append(
                f"- {row['type_slug']} :: {row['signal_key']} "
                f"({row['authority_lane']}): prevalence={float(row['prevalence_pct']):.1f}%, "
                f"pattern={row.get('pattern_label', 'Weak Pattern')}"
            )
    else:
        lines.append("")
        lines.append("No signal-group prevalence rows available.")

    lines.extend(["", "## Governance coverage"])
    if isinstance(signal_governance_coverage_df, pd.DataFrame) and not signal_governance_coverage_df.empty:
        coverage_metrics = {
            str(row["metric"]): row["value"]
            for _, row in signal_governance_coverage_df.iterrows()
            if "metric" in row and "value" in row
        }
        permission_row_count = int(pd.to_numeric(coverage_metrics.get("permission_row_count", 0), errors="coerce"))
        rows_with_effective_lane = int(
            pd.to_numeric(coverage_metrics.get("rows_with_effective_lane", 0), errors="coerce")
        )
        rows_with_candidate_lane = int(
            pd.to_numeric(coverage_metrics.get("rows_with_candidate_lane", 0), errors="coerce")
        )
        rows_with_any_governance_lane = int(
            pd.to_numeric(coverage_metrics.get("rows_with_any_governance_lane", 0), errors="coerce")
        )
        signal_assignment_pairs = int(
            pd.to_numeric(coverage_metrics.get("signal_assignment_pairs", 0), errors="coerce")
        )
        pct_governed = (
            (rows_with_any_governance_lane / permission_row_count) * 100.0
            if permission_row_count > 0
            else 0.0
        )
        lines.append("")
        lines.append(
            "These counts describe how much of the permission surface carried live governance lane metadata "
            "from Permission Intel during this run."
        )
        lines.append(f"- Permission rows evaluated: {permission_row_count}")
        lines.append(
            f"- Rows with any governance lane: {rows_with_any_governance_lane} ({pct_governed:.1f}%)"
        )
        lines.append(f"- Rows with effective governed lane: {rows_with_effective_lane}")
        lines.append(f"- Rows with candidate lane: {rows_with_candidate_lane}")
        lines.append(f"- Sample-permission signal assignment pairs: {signal_assignment_pairs}")
    else:
        lines.append("")
        lines.append("No signal governance coverage rows available.")

    lines.extend(["", "## Benchmark-eligible family signal"])
    if isinstance(family_enrichment_df, pd.DataFrame) and not family_enrichment_df.empty:
        benchmark_family = family_enrichment_df[
            pd.to_numeric(family_enrichment_df["benchmark_eligible_n_ge_3"], errors="coerce").fillna(0).astype(bool)
        ]
        top_family = (
            benchmark_family[benchmark_family["interpretation_bucket"].astype(str) != "no_signal"]
            .sort_values(
                by=["q_value_fdr", "odds_ratio", "family_support", "family_canonical", "permission"],
                ascending=[True, False, False, True, True],
                kind="mergesort",
            )
            .head(10)
        )
        if top_family.empty:
            lines.append("")
            lines.append("No family-distinguishing permissions met the current significance/odds thresholds on benchmark-eligible families.")
        else:
            lines.append("")
            lines.append("Top family-distinguishing permissions:")
            for _, row in top_family.iterrows():
                lines.append(
                    f"- {row['family_canonical']} ({row['type_slug']}, n={int(row['family_support'])}) :: {row['permission']}: "
                    f"OR={float(row['odds_ratio']):.2f}, q={float(row['q_value_fdr']):.3e}, "
                    f"bucket={row['interpretation_bucket']}, "
                    f"pattern={row.get('pattern_label', 'Weak Pattern')}"
                )
        low_support = pd.DataFrame()
        if not broad_family_df.empty and {"benchmark_eligible_n_ge_3", "family_canonical", "family_support"}.issubset(
            broad_family_df.columns
        ):
            low_support = broad_family_df[
                ~pd.to_numeric(broad_family_df["benchmark_eligible_n_ge_3"], errors="coerce").fillna(0).astype(bool)
            ][["family_canonical", "family_support"]].drop_duplicates().sort_values(
                ["family_support", "family_canonical"],
                ascending=[True, True],
                kind="mergesort",
            ).head(10)
        if not low_support.empty:
            lines.append("")
            lines.append("Benchmark-excluded families (support <3) remain visible in diagnostics:")
            for _, row in low_support.iterrows():
                lines.append(f"- {row['family_canonical']}: n={int(row['family_support'])}")
    else:
        lines.append("")
        lines.append("No family enrichment rows available.")

    if isinstance(signal_prevalence_by_family_df, pd.DataFrame) and not signal_prevalence_by_family_df.empty:
        top_family_signals = signal_prevalence_by_family_df[
            signal_prevalence_by_family_df["benchmark_eligible_n_ge_3"].astype(bool)
        ].sort_values(
            by=["prevalence_pct", "family_support", "family_canonical", "signal_key"],
            ascending=[False, False, True, True],
            kind="mergesort",
        ).head(10)
        lines.append("")
        lines.append("Secondary mixed-signal family groups (includes fingerprint/model-only lanes):")
        for _, row in top_family_signals.iterrows():
            lines.append(
                f"- {row['family_canonical']} ({row['type_slug']}, n={int(row['family_support'])}) :: "
                f"{row['signal_key']} prevalence={float(row['prevalence_pct']):.1f}%, "
                f"pattern={row.get('pattern_label', 'Weak Pattern')}"
            )
    if isinstance(signal_prevalence_by_family_behavior_safe_df, pd.DataFrame) and not signal_prevalence_by_family_behavior_safe_df.empty:
        top_family_behavior_safe = signal_prevalence_by_family_behavior_safe_df[
            signal_prevalence_by_family_behavior_safe_df["benchmark_eligible_n_ge_3"].astype(bool)
        ].sort_values(
            by=["prevalence_pct", "family_support", "family_canonical", "signal_key"],
            ascending=[False, False, True, True],
            kind="mergesort",
        ).head(10)
        lines.append("")
        lines.append("Top benchmark-eligible behavior-safe family signal groups:")
        for _, row in top_family_behavior_safe.iterrows():
            lines.append(
                f"- {row['family_canonical']} ({row['type_slug']}, n={int(row['family_support'])}) :: "
                f"{row['signal_key']} prevalence={float(row['prevalence_pct']):.1f}%, "
                f"pattern={row.get('pattern_label', 'Weak Pattern')}"
            )

    lines.extend(["", "## Temporal banker permission signals"])
    if isinstance(temporal_pattern_df, pd.DataFrame) and not temporal_pattern_df.empty:
        latest_period = str(temporal_pattern_df["period_quarter"].astype(str).max())
        latest_rows = temporal_pattern_df[
            temporal_pattern_df["period_quarter"].astype(str) == latest_period
        ].copy()
        if "pattern_level" not in latest_rows.columns:
            latest_rows["pattern_level"] = 3
        latest_rows = latest_rows.sort_values(
            by=["pattern_level", "prevalence_pct", "permission"],
            ascending=[False, False, True],
            kind="mergesort",
        ).head(6)
        lines.append("")
        lines.append(
            "Latest-quarter banker permission patterns are still static manifest interpretation only; "
            "they do not prove runtime behavior."
        )
        for _, row in latest_rows.iterrows():
            lines.append(
                f"- {row['period_quarter']} :: {row['permission']} prevalence={float(row['prevalence_pct']):.1f}% "
                f"(n={int(row['banker_sample_count'])}, pattern={row.get('pattern_label', 'Weak Pattern')}, "
                f"{row.get('pattern_confidence', 'low')})"
            )
    else:
        lines.append("")
        lines.append("No temporal banker permission pattern rows available.")

    lines.extend(["", "## Family-within-type clusters"])
    if isinstance(family_similarity_df, pd.DataFrame) and not family_similarity_df.empty:
        same_type = family_similarity_df[family_similarity_df["same_type_flag"].astype(bool)].sort_values(
            by=["cosine_similarity", "jaccard_similarity", "spearman_correlation", "family_a", "family_b"],
            ascending=[False, False, False, True, True],
            kind="mergesort",
        ).head(10)
        if same_type.empty:
            lines.append("")
            lines.append("No same-type family similarity pairs available.")
        else:
            lines.append("")
            lines.append("Closest same-type family pairs:")
            for _, row in same_type.iterrows():
                lines.append(
                    f"- {row['family_a']} vs {row['family_b']} ({row['type_a']}): "
                    f"cosine={float(row['cosine_similarity']):.3f}, "
                    f"jaccard={float(row['jaccard_similarity']):.3f}, "
                    f"spearman={float(row['spearman_correlation']):.3f}, "
                    f"pattern={row.get('pattern_label', 'Weak Pattern')} ({row.get('pattern_confidence', 'low')})"
                )
    else:
        lines.append("")
        lines.append("No family similarity rows available.")

    if isinstance(family_signal_similarity_df, pd.DataFrame) and not family_signal_similarity_df.empty:
        same_type_signal = family_signal_similarity_df[
            family_signal_similarity_df["same_type_flag"].astype(bool)
        ].sort_values(
            by=["cosine_similarity", "jaccard_similarity", "family_a", "family_b"],
            ascending=[False, False, True, True],
            kind="mergesort",
        ).head(10)
        lines.append("")
        lines.append("Secondary mixed-signal family signal-group pairs:")
        for _, row in same_type_signal.iterrows():
            lines.append(
                f"- {row['family_a']} vs {row['family_b']} ({row['type_a']}): "
                f"cosine={float(row['cosine_similarity']):.3f}, "
                f"jaccard={float(row['jaccard_similarity']):.3f}, "
                f"pattern={row.get('pattern_label', 'Weak Pattern')} ({row.get('pattern_confidence', 'low')})"
            )
    if isinstance(family_signal_similarity_behavior_safe_df, pd.DataFrame) and not family_signal_similarity_behavior_safe_df.empty:
        same_type_signal_behavior_safe = family_signal_similarity_behavior_safe_df[
            family_signal_similarity_behavior_safe_df["same_type_flag"].astype(bool)
        ].sort_values(
            by=["cosine_similarity", "jaccard_similarity", "family_a", "family_b"],
            ascending=[False, False, True, True],
            kind="mergesort",
        ).head(10)
        lines.append("")
        lines.append("Closest same-type behavior-safe family signal-group pairs:")
        for _, row in same_type_signal_behavior_safe.iterrows():
            lines.append(
                f"- {row['family_a']} vs {row['family_b']} ({row['type_a']}): "
                f"cosine={float(row['cosine_similarity']):.3f}, "
                f"jaccard={float(row['jaccard_similarity']):.3f}, "
                f"pattern={row.get('pattern_label', 'Weak Pattern')} ({row.get('pattern_confidence', 'low')})"
            )

    lines.extend(["", "## Taxonomy anomalies"])
    if isinstance(generic_summary_df, pd.DataFrame) and not generic_summary_df.empty:
        for _, row in generic_summary_df.iterrows():
            lines.append(
                f"- {row['group']}: n={int(row['sample_count'])}, "
                f"entropy_mean={float(row['permission_entropy_mean']):.3f}, "
                f"dangerous_mean={float(row['dangerous_count_strict_mean']):.3f}"
            )
    else:
        lines.append("- No generic/unresolved anomaly summary available.")

    lines.extend(["", "## Exclusions and caution lanes"])
    if isinstance(signal_prevalence_by_type_df, pd.DataFrame) and not signal_prevalence_by_type_df.empty:
        caution_keys = [
            "app_defined_scaffolding",
            "launcher_sdk_ecosystem_noise",
            "oem_vendor_ecosystem",
            "google_gms_ecosystem",
            "aosp_hidden_privileged",
        ]
        caution = signal_prevalence_by_type_df[
            signal_prevalence_by_type_df["signal_key"].isin(caution_keys)
        ].sort_values(
            by=["signal_key", "prevalence_pct", "type_slug"],
            ascending=[True, False, True],
            kind="mergesort",
        )
        lines.append("")
        lines.append("These signal groups stay available for ML/fingerprinting but are not behavior-claim-safe by default:")
        for _, row in caution.head(15).iterrows():
            lines.append(
                f"- {row['signal_key']} :: {row['type_slug']} prevalence={float(row['prevalence_pct']):.1f}% "
                f"(behavioral={'yes' if bool(row['include_in_behavioral_claims']) else 'no'})"
            )
    lines.append("- Treat behavior-safe signal tables as the primary interpretation surface; mixed signal tables are secondary diagnostics.")
    lines.append("- AOSP metadata debt remains a separate review lane and should not be promoted into hard behavior claims.")

    lines.extend(["", "## Candidate MITRE ATT&CK capability hypothesis mappings"])
    if isinstance(attack_hypotheses_df, pd.DataFrame) and not attack_hypotheses_df.empty:
        lines.append("")
        lines.append("These ATT&CK-Mobile mappings are permission-derived capability hypotheses only.")
        top_attack = attack_hypotheses_df.head(10)
        for _, row in top_attack.iterrows():
            lines.append(
                f"- {row['group_kind']} `{row['group_value']}` -> {row['attack_id']} {row['attack_name']} "
                f"({row['confidence']}; {row.get('pattern_label', 'Weak Pattern')}, "
                f"{row.get('pattern_confidence', 'low')}; matched_permissions={int(row['matched_permission_count'])})"
            )
    else:
        lines.append("- No ATT&CK-Mobile hypotheses available.")

    text = "\n".join(lines) + "\n"
    return export_markdown_with_latest(text, run_id, "permission_pattern_summary", bundle_dir)


__all__ = [
    "build_permission_trends_layout_check",
    "export_alias_map_csv",
    "export_paper_figures_index",
    "export_run_summary_onepager",
    "export_safe_claims_report",
]
