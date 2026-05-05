"""Document what each emitted figure implies and common mis-readings."""

from __future__ import annotations

from pathlib import Path
from typing import Any


_REGISTRY: dict[str, dict[str, Any]] = {
    "cohort_funnel.png": {
        "question": "How does the governed cohort shrink through alignment, supervision, and low-support pruning?",
        "subset": "`cohort_funnel.csv` stages; visualize row counts — not Macro-F1 population unless explicitly tied to train/test.",
        "normalization": "Counts are raw funnel counts; percentages (if overlaid elsewhere) must match the same numerator/denominator.",
        "signal_vs_imbalance": "Declining bars are procedural attrition — not prevalence of malicious behavior.",
        "redundant_or_misleading": "Do not cite funnel peak as supervised evaluation N without naming the downstream stage.",
        "replace_if": "Add inline annotation of aligned/post-low-support N used in modeling.",
    },
    "feature_set_macro_f1_comparison.png": {
        "question": "Which ablation/feature experiment has highest mean Macro-F1 (primary label target subset)?",
        "subset": "`signal_decomposition_summary.csv`; filtered to default family label column when column present.",
        "normalization": "Macro-F1 averaged across backend models listed in CSV — verify which models survived ranking filters.",
        "signal_vs_imbalance": "Bar ordering reflects task difficulty + feature leakage; low bars are often **expected**, not anomalies.",
        "redundant_or_misleading": "Single global mean hides per-target behavior; compare `target_validity_audit` for coarse vs fine targets.",
        "replace_if": "Split by `label_target` or annotate sample counts per experiment.",
    },
    "vendor_leakage_delta.png": {
        "question": "How much Macro-F1 is lost when parsed-family lexical columns are stripped (vs vendor_full)?",
        "subset": "`vendor_leakage_delta.csv` leakage summary rows.",
        "normalization": "Δ Macro-F1; negative deltas suggest semantic tokens carry signal (may overlap supervised label definition).",
        "signal_vs_imbalance": "Large negative deltas imply **vendor naming semantics dominate** fine-grained family classification.",
        "redundant_or_misleading": "Not a causal behavior study — lexical vendor fields correlate with taxonomy labels.",
        "replace_if": "Pair with de-lexicalized baselines (`vendor_consensus_scores_only`) and leakage audit table.",
    },
    "dangerous_permission_burden_by_type.png": {
        "question": "Do certain `type_slug` values carry proportionally higher Android dangerous permission declares?",
        "subset": "`samples_df` inner-joined permission enrichment (`build_permission_enrichment_frame`); one row per sample with enrichment.",
        "normalization": "Danger counts divided by `perm__total_count` per sample, averaged by type — proportional, not counts.",
        "signal_vs_imbalance": "Sparse types widen error bars implicitly; dominating types dominate the narrative.",
        "redundant_or_misleading": "Does not imply unique malware behavior — types differ in tooling and packer habits.",
        "replace_if": "Add count strip or confidence annotation per type_slug.",
    },
    "grouped_permission_heatmap_by_type.png": {
        "question": "Across coarse permission bundles (`perm_grp__*`), which types show higher normalized mass?",
        "subset": "Same enrichment join as dangerous burden plot; aggregates over governed cohort enrichment coverage.",
        "normalization": "Per-sample grouped sums divided by `perm__total_count`, then averaged by type — row-normalized before aggregate.",
        "signal_vs_imbalance": "Heatmap contrasts **profiles** across types — not discriminative power vs family targets.",
        "redundant_or_misleading": "Optional colormap autop-scale can inflate visual contrast among small residuals.",
        "replace_if": "Fix shared color-scale across comparable runs if readers compare snapshots.",
    },
    "permission_jsd_clustered_heatmap.png": {
        "question": "How similar are family-level BoW permission prevalence vectors (information distance)?",
        "subset": "Families observed in enriched `samples_df`; uses mean per-family permission probabilities over `perm__*` BoW dims.",
        "normalization": "Each family vector L1-normalized before pairwise Jensen-Shannon divergence.",
        "signal_vs_imbalance": "High similarity clusters may arise from taxonomy coupling or scarce families — inspect support.",
        "redundant_or_misleading": "Title says 'clustered-style' — algorithm is pairwise JSD grid, **not hierarchical clustering reorder**.",
        "replace_if": "Reorder dendrogram axes or regenerate from explicit hierarchical clustering.",
    },
    "consensus_distribution.png": {
        "question": "(Bundle) What is the AV consensus bucket prevalence in the gated cohort?",
        "subset": "Paper-style export pack under run bundles; percentages from `consensus_distribution.csv`.",
        "normalization": "Bucket percentages should sum ~100%; verify exclusions from cohort gates.",
        "signal_vs_imbalance": "Skew demonstrates vendor agreement distribution — complements permission plots only descriptively.",
        "redundant_or_misleading": "Agreement alone ≠ malicious capability without outcome linkage.",
        "replace_if": "Overlay cohort N and cohort gate parameters inline.",
    },
    "generic_consensus_vs_entropy.latest.png": {
        "question": "(Permission trends) Do high-consensus specimens show different permission entropy than low-consensus ones?",
        "subset": "Permission trends pipeline tables (see bundle `figures_dir` naming under run). Often **not copied** to flat diagnostics.",
        "normalization": "Verify whether entropy axes are Shannon over BoW declares or summaries; normalization must match figure caption.",
        "signal_vs_imbalance": "If buckets have unequal N, juxtaposed histograms confuse prevalence with effect.",
        "redundant_or_misleading": "Random-split evaluation still does **not** establish temporal extrapolation.",
        "replace_if": "Use temporal_holdout_audit.md prescriptions or annotate study design limits.",
    },
}


def write_figure_validity_audit(*, diagnostics_dir: Path, run_id: str) -> Path:
    """Write ``figure_validity_audit.md`` referencing PNGs discovered under diagnostics."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    out = diagnostics_dir / "figure_validity_audit.md"

    pngs = sorted({p.name for p in diagnostics_dir.glob("*.png")})
    mismatch = sorted(
        {
            p.name
            for p in diagnostics_dir.glob("confusion_matrix_*.png")
        }
    )
    pngs_extended = sorted(set(pngs) | set(mismatch))

    lines: list[str] = [
        "# Figure & table validity audit",
        "",
        f"Diagnostics directory scan (`run_id={run_id}`). Each figure must name the analytic population ",
        "(governed vs aligned vs train/test vs enrichment-covered). See `cohort_population_audit.md`.",
        "",
        "## Figures found",
        "",
    ]

    for name in pngs_extended:
        meta = _REGISTRY.get(name, {})
        if not meta:
            lines.extend(
                [
                    f"### `{name}`",
                    "",
                    "- **Question answered:** UNKNOWN — classify manually.",
                    "- **Data subset:** Unknown without provenance snippet; grep artifact writers referencing this basename.",
                    "- **Normalization:** Not documented here.",
                    "- **Signal vs imbalance:** May conflate rarity with novelty.",
                    "- **Redundant / misleading:** Not assessed.",
                    "- **Replacement:** Annotate subtitle with row counts + label column.",
                    "",
                ]
            )
            continue

        lines.extend(
            [
                f"### `{name}`",
                "",
                f"- **Question answered:** {meta['question']}",
                f"- **Data subset:** {meta['subset']}",
                f"- **Normalization:** {meta['normalization']}",
                f"- **Signal vs imbalance:** {meta['signal_vs_imbalance']}",
                f"- **Redundant / misleading:** {meta['redundant_or_misleading']}",
                f"- **Replace if:** {meta['replace_if']}",
                "",
            ]
        )

    lines.extend(
        [
            "## Confusion matrices",
            "",
            "Exported as `confusion_matrix_*.png` (often run-scoped path under output root — check exporter). ",
            "**Design question:** calibrated error structure for the **exact labeled active classes after low-support masking**, ",
            "not latent vendor taxonomy cardinality. Rows/columns silently drop unsupported families — captions must state filtered class list.",
            "Macro/Micro-F1 in tables must match matrix label order version.",
            "",
            "## Comparison tables (`model_comparison_summary_*.csv`, `ablation_summary_*.csv`)",
            "",
            "Treat as authoritative only after merging with `split_freeze_headline` "
            "(or `split_freeze_audit` compatibility mirror) population and cohort stage columns. ",
            "Do not interpolate headline N across rows with mismatched preprocessing flags.",
            "",
        ]
    )

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


__all__ = ["write_figure_validity_audit"]
