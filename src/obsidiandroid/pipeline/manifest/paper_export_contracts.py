"""Paper export contract/source resolution helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from obsidiandroid.pipeline.manifest.confusion_matrix_paths import find_primary_confusion_matrix


def _resolve_existing_path(*candidates: Path | None) -> Path:
    """Return the first existing path from a candidate list, or the first non-null candidate."""
    normalized = [Path(candidate) for candidate in candidates if candidate is not None]
    for candidate in normalized:
        if candidate.exists():
            return candidate
    return normalized[0] if normalized else Path()


def build_paper_export_contract(
    *,
    run_root: Path,
    diagnostics_dir: Path,
    run_id: str,
    evidence_mode: bool,
) -> dict[str, Any]:
    """Resolve the canonical Paper #2 export contract for one run."""
    required_figure_ids = {
        "fig1_pipeline_architecture",
        "fig2_type_permission_heatmap",
        "fig3_dangerous_permission_distribution_by_type",
        "fig4_family_jsd_heatmap_top12",
        "fig5_confusion_matrix_random_forest",
    }
    required_table_ids = {
        "table1_cohort_summary",
        "table2_malware_family_temporal_scope",
        "table3_model_comparison_rf_xgb_lr_fused",
        "table4_feature_ablation",
        "table5_dangerous_permission_stats_tests",
    }
    blocked_non_paper_ids = {
        "family_permission_heatmap_top12",
        "generic_consensus_vs_entropy",
        "per_family_performance_spread",
        "misclassified_samples_by_type",
    }
    figure_filename_map = {
        "fig1_pipeline_architecture": "pipeline_architecture.png",
        "fig2_type_permission_heatmap": "type_permission_heatmap.png",
        "fig3_dangerous_permission_distribution_by_type": "dangerous_permission_distribution_by_type.png",
        "fig4_family_jsd_heatmap_top12": "family_jsd_heatmap_top12.png",
        "fig5_confusion_matrix_random_forest": "confusion_matrix_random_forest.png",
    }
    table_filename_map = {
        "table1_cohort_summary": "cohort_summary.csv",
        "table2_malware_family_temporal_scope": "malware_family_temporal_scope.csv",
        "table3_model_comparison_rf_xgb_lr_fused": "model_comparison_rf_xgb_lr_fused.csv",
        "table4_feature_ablation": "feature_ablation.csv",
        "table5_dangerous_permission_stats_tests": "dangerous_permission_stats_tests.csv",
    }
    figure_stage_map = {
        "fig1_pipeline_architecture": "manifest_export",
        "fig2_type_permission_heatmap": "permission_trends_bundle.tables",
        "fig3_dangerous_permission_distribution_by_type": "permission_trends_bundle.tables",
        "fig4_family_jsd_heatmap_top12": "diagnostics.family_jsd_pairs_verification",
        "fig5_confusion_matrix_random_forest": "training_evaluation.conf_matrices",
    }
    table_stage_map = {
        "table1_cohort_summary": "manifest_export.samples",
        "table2_malware_family_temporal_scope": "manifest_export.samples",
        "table3_model_comparison_rf_xgb_lr_fused": "training_summary.diagnostics",
        "table4_feature_ablation": "ablation.diagnostics",
        "table5_dangerous_permission_stats_tests": "permission_trends_bundle.tables",
    }

    bundle_dir = run_root / "bundles" / "permission_trends"
    conf_rf = find_primary_confusion_matrix(
        run_root=run_root,
        top_model="random_forest",
        evidence_mode=True if evidence_mode else False,
    )

    figure_sources: dict[str, Path] = {}
    if conf_rf is not None:
        figure_sources["fig5_confusion_matrix_random_forest"] = conf_rf

    table_sources = {
        "table3_model_comparison_rf_xgb_lr_fused": diagnostics_dir / f"model_comparison_summary_{run_id}.csv",
        "table4_feature_ablation": _resolve_existing_path(
            diagnostics_dir / f"ablation_summary_{run_id}.csv",
            diagnostics_dir / "ablation_summary.latest.csv",
            diagnostics_dir / "ablation_summary.csv",
        ),
        "table5_dangerous_permission_stats_tests": _resolve_existing_path(
            bundle_dir / "tables" / f"dangerous_stats_tests_{run_id}.csv",
            bundle_dir / "tables" / "dangerous_stats_tests.latest.csv",
        ),
    }

    type_prev_csv = _resolve_existing_path(
        bundle_dir / "tables" / f"type_permission_prevalence_{run_id}.csv",
        bundle_dir / "tables" / "type_permission_prevalence.latest.csv",
    )
    discrim_csv = _resolve_existing_path(
        bundle_dir / "tables" / f"permission_discriminability_rank_{run_id}.csv",
        bundle_dir / "tables" / "permission_discriminability_rank.latest.csv",
    )
    dangerous_csv = _resolve_existing_path(
        bundle_dir / "tables" / f"dangerous_distribution_by_type_{run_id}.csv",
        bundle_dir / "tables" / "dangerous_distribution_by_type.latest.csv",
    )
    jsd_pairs_csv = diagnostics_dir / f"family_jsd_pairs_verification_{run_id}.csv"

    required_sources: dict[str, Path] = {
        "fig2_type_permission_heatmap:table_type_permission_prevalence": type_prev_csv,
        "fig2_type_permission_heatmap:table_permission_discriminability_rank": discrim_csv,
        "fig3_dangerous_permission_distribution_by_type:table_dangerous_distribution": dangerous_csv,
        "fig4_family_jsd_heatmap_top12:table_jsd_pairs_verification": jsd_pairs_csv,
        "fig5_confusion_matrix_random_forest:figure_confusion_matrix": (
            conf_rf if conf_rf is not None else (run_root / "__missing_confusion_matrix__")
        ),
        "table3_model_comparison_rf_xgb_lr_fused:source_model_comparison": table_sources[
            "table3_model_comparison_rf_xgb_lr_fused"
        ],
        "table4_feature_ablation:source_ablation_summary": table_sources["table4_feature_ablation"],
        "table5_dangerous_permission_stats_tests:source_dangerous_stats": table_sources[
            "table5_dangerous_permission_stats_tests"
        ],
    }

    return {
        "required_figure_ids": required_figure_ids,
        "required_table_ids": required_table_ids,
        "blocked_non_paper_ids": blocked_non_paper_ids,
        "figure_filename_map": figure_filename_map,
        "table_filename_map": table_filename_map,
        "figure_stage_map": figure_stage_map,
        "table_stage_map": table_stage_map,
        "figure_sources": figure_sources,
        "table_sources": table_sources,
        "bundle_dir": bundle_dir,
        "confusion_matrix_random_forest": conf_rf,
        "type_prevalence_csv": type_prev_csv,
        "permission_discriminability_csv": discrim_csv,
        "dangerous_distribution_csv": dangerous_csv,
        "family_jsd_pairs_csv": jsd_pairs_csv,
        "required_sources": required_sources,
    }


def missing_required_paper_sources(required_sources: dict[str, Path]) -> list[str]:
    """Return logical labels for missing required paper-export sources."""
    missing: list[str] = []
    for logical, path in required_sources.items():
        if path is None or not Path(path).exists():
            missing.append(logical)
    return missing


__all__ = ["build_paper_export_contract", "missing_required_paper_sources"]
