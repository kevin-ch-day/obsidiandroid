"""Permission trends and classification pattern reporting stage.

Canonical implementation (**Pass 70**): ``obsidiandroid.pipeline.stage_permission_trends_report``;
The supported import path is ``obsidiandroid.pipeline.stage_permission_trends_report``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common.cv_fold_config import safe_int_config_value
import obsidiandroid.governance.run_manifest as run_manifest
from obsidiandroid.pipeline.stage_results_warehouse import persist_permission_trends_results
from obsidiandroid.pipeline.permission_trends_selection import (
    filter_jsd_for_visual_families as _filter_jsd_for_visual_families,
    filter_type_prevalence_for_visuals as _filter_type_prevalence_for_visuals,
    include_banker_case_study as _include_banker_case_study,
    normalize_analysis_scope as _normalize_analysis_scope,
    normalize_figure_mode as _normalize_figure_mode,
    select_dangerous_permissions_for_heatmap as _select_dangerous_permissions_for_heatmap,
    select_discriminative_permissions as _select_discriminative_permissions,
    select_permissions_for_type_heatmap as _select_permissions_for_type_heatmap,
    select_visual_families as _select_visual_families,
)
from obsidiandroid.common.hash_utils import hash_payload

from obsidiandroid.pipeline.permission_trends.bundle_manifest import (
    export_permission_trends_bundle_manifest as _export_permission_trends_bundle_manifest,
    export_permission_trends_table_inventory_from_manifest as _export_permission_trends_table_inventory_from_manifest,
)
from obsidiandroid.pipeline.permission_trends.publish_paths import (
    compute_cohort_hash as _compute_cohort_hash,
    compute_permission_feature_hash as _compute_permission_feature_hash,
    prune_run_stamped_pngs_in_latest_bundle as _prune_run_stamped_pngs_in_latest_bundle,
)
from obsidiandroid.pipeline.permission_trends.reporting_support import (
    read_dataset_time_contract as _read_dataset_time_contract,
    read_snapshot_meta as _read_snapshot_meta,
)
from obsidiandroid.pipeline.permission_trends.constants import (
    BUNDLE_CONTRACT_NAME,
    BUNDLE_CONTRACT_VERSION,
    PERMISSION_ALIAS_MAP,
    PERMISSION_ALIAS_MAP_VERSION,
    PRIMARY_PERMISSION_VIEW,
    ReportArtifacts,
)
from obsidiandroid.pipeline.permission_trends.sample_permission_data import (
    attach_temporal_catalog_fields as _attach_temporal_catalog_fields,
    build_permission_binary_matrix as _build_permission_binary_matrix,
    build_sample_core as _build_sample_core,
    fetch_permission_aggregates as _fetch_permission_aggregates,
    fetch_permission_rows_for_samples as _fetch_permission_rows_for_samples,
    fill_permission_observations as _fill_permission_observations,
    filter_permission_rows_by_view as _filter_permission_rows_by_view,
    permission_support_floor as _permission_support_floor,
)
from obsidiandroid.pipeline.permission_trends.stats_core import (
    bh_fdr as _bh_fdr,
    build_jsd_matrix as _build_jsd_matrix,
    chi2_2x2_p_and_v as _chi2_2x2_p_and_v,
    cliffs_delta as _cliffs_delta,
    js_distance as _js_distance,
    prevalence_entropy as _prevalence_entropy,
    safe_series_mean as _safe_series_mean,
    safe_series_median as _safe_series_median,
    spearman_with_bootstrap_ci as _spearman_with_bootstrap_ci_impl,
)
from obsidiandroid.pipeline.permission_trends.stats import (
    build_dangerous_stats_tests as _build_dangerous_stats_tests_impl,
    build_permission_discriminability_rank as _build_permission_discriminability_rank_impl,
    build_consensus_correlation_report as _build_consensus_correlation_report_impl,
    build_sample_level_permission_metrics as _build_sample_level_permission_metrics_impl,
)

from obsidiandroid.pipeline.permission_trends.bundle_io import (
    copy_permission_bundle_to_latest as _copy_permission_bundle_to_latest,
    export_df_diagnostics_with_latest as _export_df_diagnostics_with_latest,
    export_df_with_latest as _export_df_with_latest,
    export_json_with_latest as _export_json_with_latest,
    export_markdown_with_latest as _export_markdown_with_latest,
    export_permission_trends_bundle_readme as _export_permission_trends_bundle_readme,
    export_text_with_latest as _export_text_with_latest,
    resolve_permission_bundle_dir as _resolve_permission_bundle_dir,
    zip_bundle as _zip_bundle,
)

from obsidiandroid.pipeline.permission_trends.figure_exports import (
    export_banker_enrichment_bar_chart as _export_banker_enrichment_bar_chart,
    export_banker_trends_line_plot as _export_banker_trends_line_plot,
    export_confusion_bar_plot as _export_confusion_bar_plot,
    export_family_permission_heatmap as _export_family_permission_heatmap,
    export_generic_scatter as _export_generic_scatter,
    export_jsd_heatmap as _export_jsd_heatmap,
    export_prevalence_heatmap as _export_prevalence_heatmap,
)
from obsidiandroid.pipeline.permission_trends.bundle_exports import (
    build_permission_trends_layout_check as _build_permission_trends_layout_check,
    export_alias_map_csv as _export_alias_map_csv,
    export_paper_figures_index as _export_paper_figures_index,
    export_permission_pattern_summary as _export_permission_pattern_summary,
    export_run_summary_onepager as _export_run_summary_onepager,
    export_safe_claims_report as _export_safe_claims_report,
)
from obsidiandroid.pipeline.permission_trends.diagnostic_exports import (
    export_jsd_pair_verification as _export_jsd_pair_verification,
    export_jsd_support_shortfall_artifact as _export_jsd_support_shortfall_artifact,
    export_selected_visual_family_registry as _export_selected_visual_family_registry,
)
from obsidiandroid.pipeline.permission_trends.consensus_audit import (
    build_consensus_distribution as _build_consensus_distribution,
    compute_consensus_metrics as _compute_consensus_metrics,
    build_generic_definition_audit as _build_generic_definition_audit,
    extract_selected_vendors as _extract_selected_vendors,
)
from obsidiandroid.governance import family_tier_authority
from obsidiandroid.orchestration.permission_features import PERMISSION_GROUP_DEFINITIONS
from obsidiandroid.governance.mobile_attack_permission_mapping import (
    mobile_attack_permission_mapping_payload as _mobile_attack_permission_mapping_payload,
)
from obsidiandroid.pipeline.permission_trends.attack_mapping import (
    build_attack_mobile_hypotheses as _build_attack_mobile_hypotheses,
    build_attack_mobile_hypotheses_markdown as _build_attack_mobile_hypotheses_markdown,
)
from obsidiandroid.pipeline.permission_trends.pattern_framework import (
    annotate_enrichment_patterns as _annotate_enrichment_patterns,
    annotate_prevalence_patterns as _annotate_prevalence_patterns,
    annotate_similarity_patterns as _annotate_similarity_patterns,
)
from obsidiandroid.diagnostics.research_validity.permission_signal_seed import (
    SIGNAL_CATALOG_ROWS as _SIGNAL_CATALOG_ROWS,
    SIGNAL_MAPPING_ROWS as _SIGNAL_MAPPING_ROWS,
    load_permission_signal_catalog_rows as _load_permission_signal_catalog_rows,
    load_permission_signal_mapping_rows as _load_permission_signal_mapping_rows,
)

def _spearman_with_bootstrap_ci(
    x: pd.Series, y: pd.Series
) -> tuple[float, float, float, float]:
    return _spearman_with_bootstrap_ci_impl(
        x,
        y,
        bootstrap_resamples=safe_int_config_value(
            getattr(app_config, "CONSENSUS_BOOTSTRAP_RESAMPLES", 2000),
            default=2000,
        ),
    )


def run_permission_trends_report_stage(
    samples_df: pd.DataFrame,
    permission_features_df: pd.DataFrame | None,
    parsed_data: dict[str, pd.DataFrame] | None,
    model_results: dict[str, Any] | None,
    run_id: str,
    profile_id: str,
    feature_df: pd.DataFrame | None = None,
) -> list[str]:
    """Generate report artifacts for permission trends and classification patterns."""
    _ = permission_features_df  # Optional ML-side matrix; reports use DB aggregates today.
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return []

    bundle_dir = _resolve_permission_bundle_dir(run_id)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    du.print_info("[REPORT] Permission trends")
    print(f"  Cohort: {len(samples_df):,} samples")
    print(f"  Bundle: {du.format_console_path(bundle_dir)}")
    removed_pngs = _prune_run_stamped_pngs_in_latest_bundle(bundle_dir)
    if removed_pngs:
        du.print_info(f"[CLEANUP] Pruned {len(removed_pngs)} legacy run-stamped PNG(s) from latest bundle.")
    analysis_scope = _normalize_analysis_scope()
    figure_mode = _normalize_figure_mode()
    include_type_figures = analysis_scope in {"all", "type"}
    include_family_figures = analysis_scope in {"all", "family"}
    include_banker_case_study = _include_banker_case_study(analysis_scope)
    include_banker_figures = include_banker_case_study and analysis_scope in {"all", "banker"}

    sample_core_df = _build_sample_core(samples_df)
    sample_core_df = _attach_temporal_catalog_fields(sample_core_df)
    permission_obs_df = _fetch_permission_aggregates()
    permission_merged_df = sample_core_df.merge(permission_obs_df, on="sample_id", how="left")
    permission_merged_df = _fill_permission_observations(permission_merged_df)
    def permission_fetch_progress(event: dict[str, Any]) -> None:
        batch = int(event.get("batch_number", 0) or 0)
        total = int(event.get("total_batches", 0) or 0)
        phase = str(event.get("phase", "")).strip().lower()
        if phase == "start":
            requested = int(event.get("requested_sample_count", 0) or 0)
            du.print_info(
                f"[REPORT] Permission retrieval: batch {batch}/{total} "
                f"({requested:,} sample IDs)"
            )
            return
        if phase == "complete":
            returned = int(event.get("returned_row_count", 0) or 0)
            cumulative = int(event.get("cumulative_rows", 0) or 0)
            duration = du.format_elapsed_duration(event.get("query_duration_sec"))
            elapsed = du.format_elapsed_duration(event.get("elapsed_sec"))
            du.print_info(f"[REPORT] Permission retrieval: batch {batch}/{total} complete")
            print(
                f"  Query: {duration} | Rows: {returned:,} | "
                f"Cumulative rows: {cumulative:,} | Stage elapsed: {elapsed}"
            )

    permission_rows_df = _fetch_permission_rows_for_samples(
        sample_core_df["sample_id"].tolist(),
        progress_callback=permission_fetch_progress,
    )
    support_floor = _permission_support_floor(len(sample_core_df))
    forced_permissions = {
        "android.permission.read_sms",
        "android.permission.receive_sms",
        "android.permission.send_sms",
        "android.permission.bind_accessibility_service",
        "android.permission.system_alert_window",
        "android.permission.request_install_packages",
    }
    view_rows = {
        "inclusive": permission_rows_df.copy(),
        "aosp_only": _filter_permission_rows_by_view(permission_rows_df, view_name="aosp_only"),
        "ecosystem": _filter_permission_rows_by_view(permission_rows_df, view_name="ecosystem"),
    }
    permission_matrix_by_view: dict[str, pd.DataFrame] = {}
    kept_permissions_by_view: dict[str, list[str]] = {}
    for view_name, rows_df in view_rows.items():
        matrix_df, kept = _build_permission_binary_matrix(
            sample_core_df=sample_core_df,
            permission_rows_df=rows_df,
            support_floor=support_floor,
            forced_permissions=forced_permissions,
        )
        permission_matrix_by_view[view_name] = matrix_df
        kept_permissions_by_view[view_name] = kept

    permission_matrix_df = permission_matrix_by_view.get(PRIMARY_PERMISSION_VIEW, pd.DataFrame())
    kept_permissions = kept_permissions_by_view.get(PRIMARY_PERMISSION_VIEW, [])
    discriminability_df = _build_permission_discriminability_rank(
        sample_core_df=sample_core_df,
        permission_matrix_df=permission_matrix_df,
        run_id=run_id,
    )

    coverage_df = _build_permission_coverage(permission_merged_df, run_id, profile_id)
    coverage_csv = _export_df_with_latest(
        coverage_df,
        run_id=run_id,
        file_stem="permission_coverage_report",
        bundle_dir=bundle_dir,
    )

    anomaly_df = _build_permission_anomalies(permission_merged_df, run_id=run_id)
    anomaly_csv = _export_df_diagnostics_with_latest(
        anomaly_df,
        run_id=run_id,
        file_stem="permission_anomaly_samples",
    )

    family_support_df = _build_family_support_distribution(sample_core_df, run_id)
    family_support_csv = _export_df_with_latest(
        family_support_df,
        run_id=run_id,
        file_stem="family_support_distribution",
        bundle_dir=bundle_dir,
    )

    dangerous_df = _build_dangerous_distribution_by_type(
        sample_core_df=sample_core_df,
        permission_rows_df=permission_rows_df,
        run_id=run_id,
    )
    dangerous_type_csv = _export_df_with_latest(
        dangerous_df,
        run_id=run_id,
        file_stem="dangerous_distribution_by_type",
        bundle_dir=bundle_dir,
    )
    temporal_trends_df = pd.DataFrame()
    temporal_trends_csv = ""
    temporal_trends_png = None
    temporal_pattern_df = pd.DataFrame()
    temporal_pattern_csv = ""
    if include_banker_case_study:
        temporal_trends_df = _build_banker_permission_trends_over_time(
            sample_core_df=sample_core_df,
            permission_rows_df=permission_rows_df,
            run_id=run_id,
        )
        temporal_trends_csv = _export_df_with_latest(
            temporal_trends_df,
            run_id=run_id,
            file_stem="banker_permission_trends_over_time",
            bundle_dir=bundle_dir,
        )
        temporal_pattern_df = _build_banker_temporal_pattern_rows(
            temporal_trends_df=temporal_trends_df,
            run_id=run_id,
        )
        temporal_pattern_csv = _export_df_with_latest(
            temporal_pattern_df,
            run_id=run_id,
            file_stem="banker_permission_trend_patterns",
            bundle_dir=bundle_dir,
        )
        temporal_trends_png = (
            _export_banker_trends_line_plot(
                trends_df=temporal_trends_df,
                run_id=run_id,
                bundle_dir=bundle_dir,
            )
            if include_banker_figures
            else None
        )

    selected_vendors = _extract_selected_vendors(feature_df)
    engine_included_count = int(feature_df.attrs.get("engine_included_count", 0)) if isinstance(feature_df, pd.DataFrame) else 0
    engine_excluded_count = int(feature_df.attrs.get("engine_excluded_count", 0)) if isinstance(feature_df, pd.DataFrame) else 0
    consensus_df = _build_consensus_distribution(
        sample_core_df=sample_core_df,
        parsed_data=parsed_data or {},
        selected_vendors=selected_vendors,
        run_id=run_id,
    )
    consensus_csv = _export_df_with_latest(
        consensus_df,
        run_id=run_id,
        file_stem="consensus_distribution",
        bundle_dir=bundle_dir,
    )

    generic_df = _build_generic_definition_audit(
        sample_core_df=sample_core_df,
        family_support_df=family_support_df,
        consensus_df=consensus_df,
        run_id=run_id,
    )
    generic_audit_csv = _export_df_with_latest(
        generic_df,
        run_id=run_id,
        file_stem="generic_definition_audit",
        bundle_dir=bundle_dir,
    )

    confusion_summary_df, confusion_detail_df = _build_type_confusion_summary(
        sample_core_df=sample_core_df,
        model_results=model_results or {},
        run_id=run_id,
    )
    confusion_summary_csv = _export_df_diagnostics_with_latest(
        confusion_summary_df,
        run_id=run_id,
        file_stem="confusion_within_vs_cross_type",
    )
    _export_df_diagnostics_with_latest(
        confusion_detail_df,
        run_id=run_id,
        file_stem="misclassified_samples_by_type",
    )
    confusion_summary_png = (
        _export_confusion_bar_plot(
            confusion_summary_df=confusion_summary_df,
            run_id=run_id,
            bundle_dir=bundle_dir,
        )
        if include_type_figures
        else None
    )

    per_family_perf_df = _build_per_family_performance_spread(
        sample_core_df=sample_core_df,
        model_results=model_results or {},
        run_id=run_id,
    )
    per_family_perf_csv = _export_df_diagnostics_with_latest(
        per_family_perf_df,
        run_id=run_id,
        file_stem="per_family_performance_spread",
    )

    type_prevalence_df, type_entropy_df = _build_type_permission_prevalence(
        sample_core_df=sample_core_df,
        permission_matrix_df=permission_matrix_df,
        run_id=run_id,
    )
    cohort_hash = _compute_cohort_hash(sample_core_df)
    permission_feature_hash = _compute_permission_feature_hash(kept_permissions_by_view)
    type_heatmap_identity = hash_payload(
        {
            "cohort_hash": cohort_hash,
            "permission_feature_hash": permission_feature_hash,
            "permission_alias_map_version": PERMISSION_ALIAS_MAP_VERSION,
            "primary_permission_view": PRIMARY_PERMISSION_VIEW,
            "figure": "type_permission_heatmap",
        }
    )
    type_prevalence_csv = _export_df_with_latest(
        type_prevalence_df,
        run_id=run_id,
        file_stem="type_permission_prevalence",
        bundle_dir=bundle_dir,
    )
    permission_prevalence_by_type_df = _build_permission_prevalence_by_type(
        sample_core_df=sample_core_df,
        permission_matrix_df=permission_matrix_df,
    )
    permission_prevalence_by_type_csv = _export_df_with_latest(
        permission_prevalence_by_type_df,
        run_id=run_id,
        file_stem="permission_prevalence_by_type",
        bundle_dir=bundle_dir,
    )
    permission_signal_rows_df = _assign_permission_signal_keys(permission_rows_df)
    permission_signal_prevalence_by_type_df = _build_signal_prevalence_by_type(
        sample_core_df=sample_core_df,
        permission_signal_rows_df=permission_signal_rows_df,
    )
    permission_signal_prevalence_by_type_csv = _export_df_with_latest(
        permission_signal_prevalence_by_type_df,
        run_id=run_id,
        file_stem="permission_signal_prevalence_by_type",
        bundle_dir=bundle_dir,
    )
    permission_signal_prevalence_by_type_behavior_safe_df = _filter_behavior_safe_signals(
        permission_signal_prevalence_by_type_df
    )
    permission_signal_prevalence_by_type_behavior_safe_csv = _export_df_with_latest(
        permission_signal_prevalence_by_type_behavior_safe_df,
        run_id=run_id,
        file_stem="permission_signal_prevalence_by_type_behavior_safe",
        bundle_dir=bundle_dir,
    )
    signal_catalog_snapshot_df = _signal_catalog_frame()
    signal_catalog_snapshot_csv = _export_df_with_latest(
        signal_catalog_snapshot_df,
        run_id=run_id,
        file_stem="permission_signal_catalog_snapshot",
        bundle_dir=bundle_dir,
        artifact_group="contracts",
    )
    signal_mapping_snapshot_df = _signal_mapping_frame()
    signal_mapping_snapshot_csv = _export_df_with_latest(
        signal_mapping_snapshot_df,
        run_id=run_id,
        file_stem="permission_signal_mapping_snapshot",
        bundle_dir=bundle_dir,
        artifact_group="contracts",
    )
    signal_governance_coverage_df = _build_permission_signal_governance_coverage(
        permission_rows_df=permission_rows_df,
        permission_signal_rows_df=permission_signal_rows_df,
        run_id=run_id,
    )
    signal_governance_coverage_csv = _export_df_with_latest(
        signal_governance_coverage_df,
        run_id=run_id,
        file_stem="permission_signal_governance_coverage",
        bundle_dir=bundle_dir,
    )
    type_capability_df = _build_type_capability_bundle_prevalence(
        sample_core_df=sample_core_df,
        permission_rows_df=permission_rows_df,
        run_id=run_id,
    )
    type_capability_csv = _export_df_with_latest(
        type_capability_df,
        run_id=run_id,
        file_stem="type_capability_bundle_prevalence",
        bundle_dir=bundle_dir,
    )
    type_entropy_csv = _export_df_with_latest(
        type_entropy_df,
        run_id=run_id,
        file_stem="type_permission_entropy",
        bundle_dir=bundle_dir,
    )
    type_heatmap_source_df = _filter_type_prevalence_for_visuals(type_prevalence_df)
    type_selected_permissions = _select_permissions_for_type_heatmap(
        method=str(getattr(app_config, "PERMISSION_SELECTION_METHOD", "discriminability")),
        top_k=safe_int_config_value(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 30), default=30),
        type_prevalence_df=type_heatmap_source_df,
        discriminability_df=discriminability_df,
        permission_rows_df=permission_rows_df,
    )
    type_heatmap_png = (
        _export_prevalence_heatmap(
            prevalence_df=type_heatmap_source_df,
            row_field="type_slug",
            value_field="prevalence",
            run_id=run_id,
            file_stem="type_permission_heatmap",
            bundle_dir=bundle_dir,
            top_k=safe_int_config_value(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 30), default=30),
            selected_permissions=type_selected_permissions,
            title="Type permission heatmap",
        )
        if include_type_figures
        else None
    )
    paper_variant_paths: list[str] = []
    top_permissions_visual = safe_int_config_value(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 30), default=30)
    top_families_visual = safe_int_config_value(getattr(app_config, "MAX_FAMILY_VISUAL_COUNT", 12), default=12)

    family_profiles_df, family_entropy_df = _build_family_permission_profiles(
        sample_core_df=sample_core_df,
        permission_matrix_df=permission_matrix_df,
        run_id=run_id,
    )
    family_profiles_csv = _export_df_with_latest(
        family_profiles_df,
        run_id=run_id,
        file_stem=f"family_permission_profiles_top{top_families_visual}",
        bundle_dir=bundle_dir,
    )
    permission_prevalence_by_family_df = _build_permission_prevalence_by_family(
        sample_core_df=sample_core_df,
        permission_matrix_df=permission_matrix_df,
    )
    permission_prevalence_by_family_csv = _export_df_with_latest(
        permission_prevalence_by_family_df,
        run_id=run_id,
        file_stem="permission_prevalence_by_family",
        bundle_dir=bundle_dir,
    )
    permission_signal_prevalence_by_family_df = _build_signal_prevalence_by_family(
        sample_core_df=sample_core_df,
        permission_signal_rows_df=permission_signal_rows_df,
    )
    permission_signal_prevalence_by_family_csv = _export_df_with_latest(
        permission_signal_prevalence_by_family_df,
        run_id=run_id,
        file_stem="permission_signal_prevalence_by_family",
        bundle_dir=bundle_dir,
    )
    permission_signal_prevalence_by_family_behavior_safe_df = _filter_behavior_safe_signals(
        permission_signal_prevalence_by_family_df
    )
    permission_signal_prevalence_by_family_behavior_safe_csv = _export_df_with_latest(
        permission_signal_prevalence_by_family_behavior_safe_df,
        run_id=run_id,
        file_stem="permission_signal_prevalence_by_family_behavior_safe",
        bundle_dir=bundle_dir,
    )
    family_capability_df = _build_family_capability_bundle_profiles(
        sample_core_df=sample_core_df,
        permission_rows_df=permission_rows_df,
        run_id=run_id,
    )
    family_capability_csv = _export_df_with_latest(
        family_capability_df,
        run_id=run_id,
        file_stem=f"family_capability_bundle_profiles_top{top_families_visual}",
        bundle_dir=bundle_dir,
    )
    family_entropy_csv = _export_df_with_latest(
        family_entropy_df,
        run_id=run_id,
        file_stem=f"family_permission_entropy_top{top_families_visual}",
        bundle_dir=bundle_dir,
    )
    main_profiles_df = (
        family_profiles_df[family_profiles_df["profile_scope"] == "main"].copy()
        if isinstance(family_profiles_df, pd.DataFrame)
        and not family_profiles_df.empty
        and "profile_scope" in family_profiles_df.columns
        else pd.DataFrame()
    )
    jsd_df = _build_jsd_matrix(
        prevalence_df=main_profiles_df,
        row_field="family_canonical",
        run_id=run_id,
    )
    jsd_csv = _export_df_with_latest(
        jsd_df,
        run_id=run_id,
        file_stem=f"family_jsd_matrix_top{top_families_visual}",
        bundle_dir=bundle_dir,
    )
    visual_families = _select_visual_families(sample_core_df=sample_core_df)
    selected_visual_families_csv = _export_selected_visual_family_registry(
        sample_core_df=sample_core_df,
        visual_families=visual_families,
        run_id=run_id,
    )
    required_visual_families = safe_int_config_value(getattr(app_config, "MAX_FAMILY_VISUAL_COUNT", 12), default=12)
    min_visual_support = safe_int_config_value(
        getattr(app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 20),
        default=20,
    )
    if len(visual_families) < required_visual_families:
        shortfall_path = _export_jsd_support_shortfall_artifact(
            run_id=run_id,
            selected_count=len(visual_families),
            required_count=required_visual_families,
            min_support=min_visual_support,
        )
        if bool(getattr(app_config, "PAPER_MODE_ENABLED", False)):
            raise RuntimeError(
                "[PAPER] JSD visual family policy shortfall: "
                f"selected={len(visual_families)} required={required_visual_families} "
                f"(min_support={min_visual_support}). See {shortfall_path}"
            )
        du.print_warning(
            "[JSD] Visual family support shortfall: "
            f"selected={len(visual_families)} required={required_visual_families} "
            f"(min_support={min_visual_support}). See {shortfall_path}"
        )
    jsd_visual_df = _filter_jsd_for_visual_families(jsd_df=jsd_df, visual_families=visual_families)
    jsd_pair_verification_csv = _export_jsd_pair_verification(
        jsd_df=jsd_visual_df,
        run_id=run_id,
        bundle_dir=bundle_dir,
        file_stem=f"family_jsd_pairs_top{top_families_visual}",
    )
    jsd_png = (
        _export_jsd_heatmap(
            jsd_df=jsd_visual_df,
            run_id=run_id,
            file_stem=f"family_jsd_heatmap_top{top_families_visual}",
            bundle_dir=bundle_dir,
        )
        if include_family_figures
        else None
    )
    family_heatmap_png = (
        _export_family_permission_heatmap(
            family_profiles_df=family_profiles_df,
            visual_families=visual_families,
            run_id=run_id,
            file_stem=f"family_permission_heatmap_top{top_families_visual}",
            bundle_dir=bundle_dir,
        )
        if include_family_figures
        else None
    )

    banker_enrichment_df = pd.DataFrame()
    banker_enrichment_csv = ""
    banker_top15_csv = ""
    banker_bar_png = None
    banker_enrichment_inclusive_df = pd.DataFrame()
    banker_enrichment_ecosystem_df = pd.DataFrame()
    banker_enrichment_by_view_df = pd.DataFrame()
    if include_banker_case_study:
        banker_enrichment_df = _build_banker_permission_enrichment(
            sample_core_df=sample_core_df,
            permission_matrix_df=permission_matrix_df,
            run_id=run_id,
            forced_permissions=forced_permissions,
        )
        banker_enrichment_csv = _export_df_with_latest(
            banker_enrichment_df,
            run_id=run_id,
            file_stem="banker_permission_enrichment",
            bundle_dir=bundle_dir,
        )
        banker_top15_csv = _export_df_with_latest(
            banker_enrichment_df.sort_values("odds_ratio", ascending=False).head(15),
            run_id=run_id,
            file_stem="banker_permission_enrichment_top15",
            bundle_dir=bundle_dir,
        )
        banker_bar_png = (
            _export_banker_enrichment_bar_chart(
                banker_df=banker_enrichment_df,
                run_id=run_id,
                bundle_dir=bundle_dir,
            )
            if include_banker_figures
            else None
        )
        banker_enrichment_inclusive_df = _build_banker_permission_enrichment(
            sample_core_df=sample_core_df,
            permission_matrix_df=permission_matrix_by_view.get("inclusive", pd.DataFrame()),
            run_id=run_id,
            forced_permissions=forced_permissions,
        )
        banker_enrichment_ecosystem_df = _build_banker_permission_enrichment(
            sample_core_df=sample_core_df,
            permission_matrix_df=permission_matrix_by_view.get("ecosystem", pd.DataFrame()),
            run_id=run_id,
            forced_permissions=forced_permissions,
        )
        _export_df_with_latest(
            banker_enrichment_inclusive_df,
            run_id=run_id,
            file_stem="banker_permission_enrichment_inclusive",
            bundle_dir=bundle_dir,
        )
        _export_df_with_latest(
            banker_enrichment_ecosystem_df,
            run_id=run_id,
            file_stem="banker_permission_enrichment_ecosystem",
            bundle_dir=bundle_dir,
        )
        banker_enrichment_by_view_df = pd.concat(
            [
                banker_enrichment_df.assign(view_mode=PRIMARY_PERMISSION_VIEW),
                banker_enrichment_inclusive_df.assign(view_mode="inclusive"),
                banker_enrichment_ecosystem_df.assign(view_mode="ecosystem"),
            ],
            ignore_index=True,
        )

    discriminability_csv = _export_df_with_latest(
        discriminability_df,
        run_id=run_id,
        file_stem="permission_discriminability_rank",
        bundle_dir=bundle_dir,
    )
    if bool(getattr(app_config, "PAPER_MODE_ENABLED", False)) and include_type_figures:
        top_k_paper = safe_int_config_value(getattr(app_config, "PAPER_HEATMAP_TOP_K", 35), default=35)
        top_k_dangerous = safe_int_config_value(
            getattr(app_config, "PAPER_DANGEROUS_HEATMAP_TOP_K", 25),
            default=25,
        )
        discrim_permissions = _select_discriminative_permissions(
            discriminability_df=discriminability_df,
            top_k=top_k_paper,
        )
        dangerous_permissions = _select_dangerous_permissions_for_heatmap(
            permission_rows_df=permission_rows_df,
            type_prevalence_df=type_prevalence_df,
            top_k=top_k_dangerous,
        )
        paper_discrim_png = _export_prevalence_heatmap(
            prevalence_df=type_heatmap_source_df,
            row_field="type_slug",
            value_field="prevalence",
            run_id=run_id,
            file_stem=f"type_permission_heatmap_discriminative_top{len(discrim_permissions)}",
            bundle_dir=bundle_dir,
            selected_permissions=discrim_permissions,
            title=f"Type permission heatmap (top {len(discrim_permissions)} discriminative)",
        )
        paper_dangerous_png = _export_prevalence_heatmap(
            prevalence_df=type_heatmap_source_df,
            row_field="type_slug",
            value_field="prevalence",
            run_id=run_id,
            file_stem="type_permission_heatmap_dangerous_only",
            bundle_dir=bundle_dir,
            selected_permissions=dangerous_permissions,
            title=f"Type permission heatmap (top {len(dangerous_permissions)} dangerous)",
        )
        for maybe_path in [paper_discrim_png, paper_dangerous_png]:
            if isinstance(maybe_path, str):
                paper_variant_paths.append(maybe_path)
    # The primary view was already computed above for the main report. Reuse
    # those frames for warehouse/view comparisons instead of recomputing the
    # same group-by, JSD, and discriminability work a second time.
    type_prevalence_view_frames: list[pd.DataFrame] = (
        [type_prevalence_df.assign(view_mode=PRIMARY_PERMISSION_VIEW)]
        if not type_prevalence_df.empty
        else []
    )
    family_profiles_view_frames: list[pd.DataFrame] = (
        [family_profiles_df.assign(view_mode=PRIMARY_PERMISSION_VIEW)]
        if not family_profiles_df.empty
        else []
    )
    group_entropy_view_frames: list[pd.DataFrame] = []
    if not type_entropy_df.empty:
        type_entropy_primary = type_entropy_df.copy()
        type_entropy_primary["group_type"] = "type"
        type_entropy_primary["group_key"] = type_entropy_primary["type_slug"].astype(str)
        type_entropy_primary["view_mode"] = PRIMARY_PERMISSION_VIEW
        group_entropy_view_frames.append(
            type_entropy_primary[
                [
                    "run_id",
                    "group_type",
                    "group_key",
                    "view_mode",
                    "sample_count",
                    "permission_entropy",
                    "effective_diversity",
                ]
            ]
        )
    if not family_entropy_df.empty:
        family_entropy_primary = family_entropy_df.copy()
        family_entropy_primary["group_type"] = "family"
        family_entropy_primary["group_key"] = family_entropy_primary["family_id"].astype(str)
        family_entropy_primary["view_mode"] = PRIMARY_PERMISSION_VIEW
        group_entropy_view_frames.append(
            family_entropy_primary[
                [
                    "run_id",
                    "group_type",
                    "group_key",
                    "view_mode",
                    "sample_count",
                    "permission_entropy",
                    "effective_diversity",
                ]
            ]
        )
    family_jsd_view_frames: list[pd.DataFrame] = (
        [jsd_df.assign(view_mode=PRIMARY_PERMISSION_VIEW)] if not jsd_df.empty else []
    )
    discriminability_view_frames: list[pd.DataFrame] = (
        [discriminability_df.assign(view_mode=PRIMARY_PERMISSION_VIEW)]
        if not discriminability_df.empty
        else []
    )
    for view_name, matrix_df in permission_matrix_by_view.items():
        if view_name == PRIMARY_PERMISSION_VIEW:
            continue
        view_prev_df, view_type_entropy_df = _build_type_permission_prevalence(
            sample_core_df=sample_core_df,
            permission_matrix_df=matrix_df,
            run_id=run_id,
        )
        if not view_prev_df.empty:
            view_prev_df = view_prev_df.copy()
            view_prev_df["view_mode"] = view_name
            type_prevalence_view_frames.append(view_prev_df)
        if not view_type_entropy_df.empty:
            type_entropy_view = view_type_entropy_df.copy()
            type_entropy_view["group_type"] = "type"
            type_entropy_view["group_key"] = type_entropy_view["type_slug"].astype(str)
            type_entropy_view["view_mode"] = view_name
            group_entropy_view_frames.append(
                type_entropy_view[
                    [
                        "run_id",
                        "group_type",
                        "group_key",
                        "view_mode",
                        "sample_count",
                        "permission_entropy",
                        "effective_diversity",
                    ]
                ]
            )
        view_family_profiles_df, view_family_entropy_df = _build_family_permission_profiles(
            sample_core_df=sample_core_df,
            permission_matrix_df=matrix_df,
            run_id=run_id,
        )
        if not view_family_profiles_df.empty:
            view_family_profiles_df = view_family_profiles_df.copy()
            view_family_profiles_df["view_mode"] = view_name
            family_profiles_view_frames.append(view_family_profiles_df)
            view_main_profiles_df = view_family_profiles_df[view_family_profiles_df["profile_scope"] == "main"].copy()
            view_jsd_df = _build_jsd_matrix(
                prevalence_df=view_main_profiles_df,
                row_field="family_canonical",
                run_id=run_id,
            )
            if not view_jsd_df.empty:
                view_jsd_df = view_jsd_df.copy()
                view_jsd_df["view_mode"] = view_name
                family_jsd_view_frames.append(view_jsd_df)
        if not view_family_entropy_df.empty:
            fam_entropy_view = view_family_entropy_df.copy()
            fam_entropy_view["group_type"] = "family"
            fam_entropy_view["group_key"] = fam_entropy_view["family_id"].astype(str)
            fam_entropy_view["view_mode"] = view_name
            group_entropy_view_frames.append(
                fam_entropy_view[
                    [
                        "run_id",
                        "group_type",
                        "group_key",
                        "view_mode",
                        "sample_count",
                        "permission_entropy",
                        "effective_diversity",
                    ]
                ]
            )
        view_disc_df = _build_permission_discriminability_rank(
            sample_core_df=sample_core_df,
            permission_matrix_df=matrix_df,
            run_id=run_id,
        )
        if not view_disc_df.empty:
            view_disc_df = view_disc_df.copy()
            view_disc_df["view_mode"] = view_name
            discriminability_view_frames.append(view_disc_df)

    generic_summary_df = _build_generic_vs_non_generic_summary(
        sample_core_df=sample_core_df,
        permission_rows_df=permission_rows_df,
        permission_matrix_df=permission_matrix_df,
        consensus_df=consensus_df,
        run_id=run_id,
    )
    generic_summary_csv = _export_df_with_latest(
        generic_summary_df,
        run_id=run_id,
        file_stem="generic_vs_non_generic_summary",
        bundle_dir=bundle_dir,
    )
    generic_scatter_png = (
        _export_generic_scatter(
            sample_core_df=sample_core_df,
            permission_rows_df=permission_rows_df,
            consensus_df=consensus_df,
            run_id=run_id,
            bundle_dir=bundle_dir,
        )
        if include_family_figures
        else None
    )
    consensus_corr_df, consensus_corr_text = _build_consensus_correlation_report(
        sample_core_df=sample_core_df,
        permission_rows_df=permission_rows_df,
        consensus_df=consensus_df,
        run_id=run_id,
    )
    consensus_corr_csv = _export_df_with_latest(
        consensus_corr_df,
        run_id=run_id,
        file_stem="consensus_correlation_report",
        bundle_dir=bundle_dir,
    )
    consensus_corr_txt = _export_text_with_latest(
        text=consensus_corr_text,
        run_id=run_id,
        file_stem="consensus_correlation_report",
        bundle_dir=bundle_dir,
    )
    permission_type_enrichment_df = _build_permission_type_enrichment(
        sample_core_df=sample_core_df,
        permission_matrix_df=permission_matrix_df,
    )
    permission_type_enrichment_csv = _export_df_with_latest(
        permission_type_enrichment_df,
        run_id=run_id,
        file_stem="permission_type_enrichment",
        bundle_dir=bundle_dir,
    )
    permission_family_enrichment_df = _build_permission_family_enrichment(
        sample_core_df=sample_core_df,
        permission_matrix_df=permission_matrix_df,
    )
    permission_family_enrichment_csv = _export_df_with_latest(
        permission_family_enrichment_df,
        run_id=run_id,
        file_stem="permission_family_enrichment",
        bundle_dir=bundle_dir,
    )
    family_permission_similarity_df = _build_family_permission_similarity(
        family_prevalence_df=permission_prevalence_by_family_df,
    )
    family_permission_similarity_csv = _export_df_with_latest(
        family_permission_similarity_df,
        run_id=run_id,
        file_stem="family_permission_similarity",
        bundle_dir=bundle_dir,
    )
    family_signal_similarity_df = _build_family_signal_similarity(
        family_signal_prevalence_df=permission_signal_prevalence_by_family_df[
            permission_signal_prevalence_by_family_df["benchmark_eligible_n_ge_3"].astype(bool)
        ].copy(),
    )
    family_signal_similarity_csv = _export_df_with_latest(
        family_signal_similarity_df,
        run_id=run_id,
        file_stem="family_signal_similarity",
        bundle_dir=bundle_dir,
    )
    family_signal_similarity_behavior_safe_df = _build_family_signal_similarity(
        family_signal_prevalence_df=permission_signal_prevalence_by_family_behavior_safe_df[
            permission_signal_prevalence_by_family_behavior_safe_df["benchmark_eligible_n_ge_3"].astype(bool)
        ].copy(),
    )
    family_signal_similarity_behavior_safe_csv = _export_df_with_latest(
        family_signal_similarity_behavior_safe_df,
        run_id=run_id,
        file_stem="family_signal_similarity_behavior_safe",
        bundle_dir=bundle_dir,
    )
    type_permission_similarity_df = _build_type_permission_similarity(
        type_prevalence_df=permission_prevalence_by_type_df,
    )
    type_permission_similarity_csv = _export_df_with_latest(
        type_permission_similarity_df,
        run_id=run_id,
        file_stem="type_permission_similarity",
        bundle_dir=bundle_dir,
    )
    attack_hypotheses_type_df = _build_attack_mobile_hypotheses(
        prevalence_df=permission_prevalence_by_type_df,
        run_id=run_id,
        group_field="type_slug",
        group_kind="type",
        sample_count_field="n_samples",
        prevalence_field="prevalence_pct",
    )
    attack_hypotheses_family_df = _build_attack_mobile_hypotheses(
        prevalence_df=permission_prevalence_by_family_df[
            permission_prevalence_by_family_df["benchmark_eligible_n_ge_3"].astype(bool)
        ].copy(),
        run_id=run_id,
        group_field="family_canonical",
        group_kind="family",
        sample_count_field="family_support",
        prevalence_field="prevalence_pct",
    )
    attack_hypotheses_df = pd.concat(
        [frame for frame in [attack_hypotheses_type_df, attack_hypotheses_family_df] if isinstance(frame, pd.DataFrame) and not frame.empty],
        ignore_index=True,
    ) if (not attack_hypotheses_type_df.empty or not attack_hypotheses_family_df.empty) else pd.DataFrame()
    attack_hypotheses_csv = _export_df_with_latest(
        attack_hypotheses_df,
        run_id=run_id,
        file_stem="attack_mobile_hypotheses",
        bundle_dir=bundle_dir,
    )
    attack_hypotheses_json = _export_json_with_latest(
        payload={
            "run_id": run_id,
            "mapping": _mobile_attack_permission_mapping_payload(),
            "rows": attack_hypotheses_df.to_dict(orient="records") if isinstance(attack_hypotheses_df, pd.DataFrame) else [],
        },
        run_id=run_id,
        file_stem="attack_mobile_hypotheses",
        bundle_dir=bundle_dir,
    )
    attack_hypotheses_md = _export_markdown_with_latest(
        text=_build_attack_mobile_hypotheses_markdown(
            hypotheses_df=attack_hypotheses_df,
            run_id=run_id,
        ),
        run_id=run_id,
        file_stem="attack_mobile_hypotheses",
        bundle_dir=bundle_dir,
    )
    dangerous_stats_df = _build_dangerous_stats_tests(
        sample_core_df=sample_core_df,
        permission_rows_df=permission_rows_df,
        run_id=run_id,
    )
    dangerous_stats_csv = _export_df_with_latest(
        dangerous_stats_df,
        run_id=run_id,
        file_stem="dangerous_stats_tests",
        bundle_dir=bundle_dir,
    )
    banker_clusters_df = pd.DataFrame()
    banker_cluster_profiles_df = pd.DataFrame()
    banker_clusters_csv = ""
    banker_cluster_profiles_csv = ""
    if include_banker_case_study:
        banker_clusters_df, banker_cluster_profiles_df = _build_banker_family_pattern_clusters(
            sample_core_df=sample_core_df,
            family_profiles_df=family_profiles_df,
            run_id=run_id,
        )
        banker_clusters_csv = _export_df_with_latest(
            banker_clusters_df,
            run_id=run_id,
            file_stem="banker_family_pattern_clusters",
            bundle_dir=bundle_dir,
        )
        banker_cluster_profiles_csv = _export_df_with_latest(
            banker_cluster_profiles_df,
            run_id=run_id,
            file_stem="banker_family_cluster_profiles",
            bundle_dir=bundle_dir,
        )

    bundle_metadata = _build_bundle_metadata(
        run_id=run_id,
        profile_id=profile_id,
        sample_core_df=sample_core_df,
        coverage_df=coverage_df,
        consensus_df=consensus_df,
        family_support_df=family_support_df,
        selected_vendors=selected_vendors,
        engine_included_count=engine_included_count,
        engine_excluded_count=engine_excluded_count,
        permission_support_floor=support_floor,
        kept_permission_count=len(kept_permissions),
        kept_permissions_by_view=kept_permissions_by_view,
        analysis_scope=analysis_scope,
        figure_mode=figure_mode,
        cohort_hash=cohort_hash,
        permission_feature_hash=permission_feature_hash,
        type_heatmap_identity=type_heatmap_identity,
        dataset_time_contract=_read_dataset_time_contract(),
    )
    dataset_time_contract_json = _export_json_with_latest(
        payload=bundle_metadata.get("dataset_time_contract", {}),
        run_id=run_id,
        file_stem="dataset_time_contract",
        bundle_dir=bundle_dir,
    )
    bundle_metadata_json = _export_json_with_latest(
        payload=bundle_metadata,
        run_id=run_id,
        file_stem="bundle_metadata",
        bundle_dir=bundle_dir,
    )
    alias_map_json = _export_json_with_latest(
        payload={
            "permission_alias_map_version": PERMISSION_ALIAS_MAP_VERSION,
            "alias_map": PERMISSION_ALIAS_MAP,
        },
        run_id=run_id,
        file_stem="permission_alias_map",
        bundle_dir=bundle_dir,
    )
    alias_map_csv = _export_alias_map_csv(run_id=run_id, bundle_dir=bundle_dir)
    layout_check_payload = _build_permission_trends_layout_check(bundle_dir=bundle_dir)
    layout_check_json = _export_json_with_latest(
        payload=layout_check_payload,
        run_id=run_id,
        file_stem="permission_trends_layout_check",
        bundle_dir=bundle_dir,
    )

    safe_claims_txt = _export_safe_claims_report(
        run_id=run_id,
        bundle_dir=bundle_dir,
        coverage_df=coverage_df,
        banker_enrichment_df=banker_enrichment_df,
        dangerous_df=dangerous_df,
        consensus_df=consensus_df,
        selected_vendor_count=len(selected_vendors),
        select_banker_summary_rows=_select_banker_summary_rows,
    )
    figures_index_md = _export_paper_figures_index(
        run_id=run_id,
        bundle_dir=bundle_dir,
        type_heatmap_png=type_heatmap_png,
        banker_bar_png=banker_bar_png,
        generic_scatter_png=generic_scatter_png,
        jsd_png=jsd_png,
        temporal_trends_png=temporal_trends_png,
        banker_enrichment_csv=banker_enrichment_csv,
    )
    run_summary_md = _export_run_summary_onepager(
        run_id=run_id,
        profile_id=profile_id,
        bundle_dir=bundle_dir,
        coverage_df=coverage_df,
        dangerous_df=dangerous_df,
        consensus_df=consensus_df,
        bundle_metadata=bundle_metadata,
        banker_enrichment_df=banker_enrichment_df,
        select_banker_summary_rows=_select_banker_summary_rows,
        discriminability_df=discriminability_df,
        type_entropy_df=type_entropy_df,
        family_profiles_df=family_profiles_df,
        type_capability_df=type_capability_df,
        family_capability_df=family_capability_df,
        attack_hypotheses_df=attack_hypotheses_df,
    )
    permission_pattern_summary_md = _export_permission_pattern_summary(
        run_id=run_id,
        bundle_dir=bundle_dir,
        prevalence_by_type_df=permission_prevalence_by_type_df,
        prevalence_by_family_df=permission_prevalence_by_family_df,
        signal_prevalence_by_type_df=permission_signal_prevalence_by_type_df,
        signal_prevalence_by_type_behavior_safe_df=permission_signal_prevalence_by_type_behavior_safe_df,
        signal_prevalence_by_family_df=permission_signal_prevalence_by_family_df,
        signal_prevalence_by_family_behavior_safe_df=permission_signal_prevalence_by_family_behavior_safe_df,
        family_signal_similarity_df=family_signal_similarity_df,
        family_signal_similarity_behavior_safe_df=family_signal_similarity_behavior_safe_df,
        signal_governance_coverage_df=signal_governance_coverage_df,
        type_enrichment_df=permission_type_enrichment_df,
        family_enrichment_df=permission_family_enrichment_df,
        family_similarity_df=family_permission_similarity_df,
        attack_hypotheses_df=attack_hypotheses_df,
        generic_summary_df=generic_summary_df,
        temporal_pattern_df=temporal_pattern_df,
    )
    bundle_readme_path = _export_permission_trends_bundle_readme(run_id=run_id, bundle_dir=bundle_dir)

    bundle_zip_path = _zip_bundle(bundle_dir) if bool(getattr(app_config, "ENABLE_PERMISSION_TRENDS_BUNDLE_ZIP", False)) else ""
    if not bundle_zip_path:
        du.print_info("[REPORT] Bundle ZIP export disabled; keeping run-scoped folder only.")

    artifacts = ReportArtifacts(
        coverage_csv=coverage_csv,
        anomaly_csv=anomaly_csv,
        family_support_csv=family_support_csv,
        dangerous_type_csv=dangerous_type_csv,
        consensus_csv=consensus_csv,
        generic_audit_csv=generic_audit_csv,
        confusion_summary_csv=confusion_summary_csv,
        confusion_summary_png=confusion_summary_png,
        per_family_perf_csv=per_family_perf_csv,
        dangerous_stats_csv=dangerous_stats_csv,
        consensus_correlation_csv=consensus_corr_csv,
        consensus_correlation_txt=consensus_corr_txt,
        banker_clusters_csv=banker_clusters_csv,
        banker_cluster_profiles_csv=banker_cluster_profiles_csv,
        temporal_trends_csv=temporal_trends_csv,
        temporal_trends_png=temporal_trends_png,
        bundle_metadata_json=bundle_metadata_json,
        bundle_zip=bundle_zip_path,
    )
    paths = [value for value in artifacts.__dict__.values() if isinstance(value, str) and value]
    paths.extend(
        [
            dataset_time_contract_json,
            alias_map_json,
            alias_map_csv,
            layout_check_json,
            safe_claims_txt,
            figures_index_md,
            run_summary_md,
            permission_pattern_summary_md,
        ]
    )
    for extra_path in [
        type_prevalence_csv,
        permission_prevalence_by_type_csv,
        permission_signal_prevalence_by_type_csv,
        permission_signal_prevalence_by_type_behavior_safe_csv,
        type_entropy_csv,
        family_profiles_csv,
        permission_prevalence_by_family_csv,
        permission_signal_prevalence_by_family_csv,
        permission_signal_prevalence_by_family_behavior_safe_csv,
        family_capability_csv,
        family_entropy_csv,
        banker_enrichment_csv,
        banker_top15_csv,
        discriminability_csv,
        type_capability_csv,
        generic_summary_csv,
        jsd_csv,
        consensus_corr_csv,
        permission_type_enrichment_csv,
        permission_family_enrichment_csv,
        family_permission_similarity_csv,
        family_signal_similarity_csv,
        family_signal_similarity_behavior_safe_csv,
        type_permission_similarity_csv,
        signal_governance_coverage_csv,
        dangerous_stats_csv,
        banker_clusters_csv,
        banker_cluster_profiles_csv,
        selected_visual_families_csv,
        jsd_pair_verification_csv,
        signal_catalog_snapshot_csv,
        signal_mapping_snapshot_csv,
        temporal_pattern_csv,
    ]:
        if isinstance(extra_path, str) and extra_path:
            paths.append(extra_path)
    for maybe_png in [type_heatmap_png, family_heatmap_png, banker_bar_png, generic_scatter_png, jsd_png]:
        if isinstance(maybe_png, str):
            paths.append(maybe_png)
    if isinstance(temporal_trends_png, str):
        paths.append(temporal_trends_png)
    for extra_path in [attack_hypotheses_csv, attack_hypotheses_json, attack_hypotheses_md]:
        if isinstance(extra_path, str) and extra_path:
            paths.append(extra_path)
    paths.extend(paper_variant_paths)
    if isinstance(bundle_readme_path, str) and bundle_readme_path:
        paths.append(bundle_readme_path)
    bundle_manifest_json = _export_permission_trends_bundle_manifest(
        run_id=run_id,
        bundle_dir=bundle_dir,
        top_families_visual=top_families_visual,
        min_visual_family_support=min_visual_support,
        top_permissions=top_permissions_visual,
        artifact_paths=paths,
    )
    if isinstance(bundle_manifest_json, str) and bundle_manifest_json:
        paths.append(bundle_manifest_json)
        table_inventory_csv = _export_permission_trends_table_inventory_from_manifest(
            bundle_dir=bundle_dir,
            run_id=run_id,
            manifest_path=bundle_manifest_json,
        )
        if isinstance(table_inventory_csv, str) and table_inventory_csv:
            paths.append(table_inventory_csv)
    if bool(getattr(app_config, "ENABLE_RESULTS_WAREHOUSE_EXPORT", False)):
        try:
            persist_permission_trends_results(
                run_id=run_id,
                profile_id=profile_id,
                bundle_metadata=bundle_metadata,
                sample_core_df=sample_core_df,
                coverage_df=coverage_df,
                dangerous_df=dangerous_df,
                type_prevalence_df=type_prevalence_df,
                family_profiles_df=family_profiles_df,
                type_entropy_df=type_entropy_df,
                family_entropy_df=family_entropy_df,
                jsd_df=jsd_df,
                banker_enrichment_df=banker_enrichment_df,
                discriminability_df=discriminability_df,
                consensus_df=consensus_df,
                per_family_perf_df=per_family_perf_df,
                artifact_paths=paths,
                type_prevalence_by_view_df=(
                    pd.concat(type_prevalence_view_frames, ignore_index=True)
                    if type_prevalence_view_frames
                    else pd.DataFrame()
                ),
                family_profiles_by_view_df=(
                    pd.concat(family_profiles_view_frames, ignore_index=True)
                    if family_profiles_view_frames
                    else pd.DataFrame()
                ),
                group_entropy_by_view_df=(
                    pd.concat(group_entropy_view_frames, ignore_index=True)
                    if group_entropy_view_frames
                    else pd.DataFrame()
                ),
                family_jsd_by_view_df=(
                    pd.concat(family_jsd_view_frames, ignore_index=True)
                    if family_jsd_view_frames
                    else pd.DataFrame()
                ),
                banker_enrichment_by_view_df=banker_enrichment_by_view_df,
                discriminability_by_view_df=(
                    pd.concat(discriminability_view_frames, ignore_index=True)
                    if discriminability_view_frames
                    else pd.DataFrame()
                ),
                banker_cluster_assignments_df=banker_clusters_df,
                banker_cluster_profiles_df=banker_cluster_profiles_df,
                temporal_trends_df=temporal_trends_df,
            )
        except Exception as exc:
            du.print_warning(f"[WAREHOUSE] Skipped DB persistence due to error: {exc}")
    latest_copy_dir = None
    if bool(getattr(app_config, "ENABLE_PERMISSION_TRENDS_LATEST_MIRROR", False)):
        latest_copy_dir = _copy_permission_bundle_to_latest(bundle_dir=bundle_dir)
    else:
        du.print_info("[REPORT] Latest bundle mirror disabled; using run-scoped bundle as source of truth.")
    # Paper exports are now authored strictly in stage_manifest only.
    # Keep this stage focused on research bundle production.
    du.print_info("[REPORT] Skipping legacy bundle->paper_exports mirror (stage_manifest is authoritative).")
    setattr(app_config, "RUNTIME_PERMISSION_BUNDLE_DIR", str(bundle_dir))
    setattr(app_config, "RUNTIME_PERMISSION_BUNDLE_ZIP", str(artifacts.bundle_zip))
    if latest_copy_dir is not None:
        setattr(app_config, "RUNTIME_PERMISSION_BUNDLE_LATEST_DIR", str(latest_copy_dir))
    du.print_info(f"[REPORT] Permission trends artifacts:{du.format_console_path(bundle_dir)}")
    return paths


def _build_permission_coverage(df: pd.DataFrame, run_id: str, profile_id: str) -> pd.DataFrame:
    n_samples = max(len(df), 1)
    with_rows = int((df["permission_obs_rows"] > 0).sum())
    zero_rows = int((df["permission_obs_rows"] == 0).sum())
    missing_sha = int((df["sha256"].str.len() != 64).sum())
    missing_pkg = int((df["android_package_name"] == "").sum())
    only_common = int(
        ((df["permission_obs_rows"] > 0) & (df["permission_obs_rows"] == df["permission_common_rows"])).sum()
    )
    perm_le2 = int((df["permission_unique_count"] <= 2).sum())
    row = {
        "run_id": run_id,
        "profile_id": profile_id,
        "sample_count": int(len(df)),
        "samples_with_permission_rows": with_rows,
        "samples_zero_permission_rows": zero_rows,
        "samples_missing_sha256": missing_sha,
        "samples_missing_package_name": missing_pkg,
        "pct_with_permission_rows": round(with_rows / n_samples, 6),
        "pct_missing_permission_rows": round(1.0 - (with_rows / n_samples), 6),
        "pct_zero_permissions": round(zero_rows / n_samples, 6),
        "pct_missing_sha256": round(missing_sha / n_samples, 6),
        "pct_missing_package_name": round(missing_pkg / n_samples, 6),
        "pct_samples_only_common_perms": round(only_common / n_samples, 6),
        "pct_samples_le2_permissions": round(perm_le2 / n_samples, 6),
        "mean_unique_permissions": round(float(df["permission_unique_count"].mean()), 6),
        "std_unique_permissions": round(float(df["permission_unique_count"].std(ddof=0)), 6),
        "median_unique_permissions": round(float(df["permission_unique_count"].median()), 6),
    }
    return pd.DataFrame([row])


def _build_permission_anomalies(df: pd.DataFrame, run_id: str) -> pd.DataFrame:
    anomalies: list[dict[str, Any]] = []
    subset_b = df[(df["android_permission_count"] > 0) & (df["permission_obs_rows"] == 0)]
    for _, row in subset_b.iterrows():
        anomalies.append(
            {
                "run_id": str(run_id),
                "sample_id": int(row["sample_id"]),
                "sha256": str(row["sha256"]),
                "reason": "catalog_permission_count_nonzero_but_missing_obs_rows",
            }
        )
    subset_c = df[df["sha256"].astype(str).str.len() != 64]
    for _, row in subset_c.iterrows():
        anomalies.append(
            {
                "run_id": str(run_id),
                "sample_id": int(row["sample_id"]),
                "sha256": str(row["sha256"]),
                "reason": "missing_or_invalid_sha256",
            }
        )
    subset_d = df[df["android_package_name"].astype(str).str.strip() == ""]
    for _, row in subset_d.iterrows():
        anomalies.append(
            {
                "run_id": str(run_id),
                "sample_id": int(row["sample_id"]),
                "sha256": str(row["sha256"]),
                "reason": "missing_package_name",
            }
        )

    # Keep anomaly exports scoped to the active analysis snapshot to avoid
    # bloating artifacts with unrelated global ingestion history rows.
    out = pd.DataFrame(anomalies)
    if out.empty:
        return pd.DataFrame(columns=["run_id", "sample_id", "sha256", "reason"])
    out = out.drop_duplicates(subset=["sample_id", "reason"]).sort_values(["reason", "sample_id"])
    return out.reset_index(drop=True)


def _build_family_support_distribution(sample_core_df: pd.DataFrame, run_id: str) -> pd.DataFrame:
    support_df = _family_support_frame(sample_core_df, benchmark_min_support=3)
    if support_df.empty:
        return pd.DataFrame(
            columns=[
                "family_id",
                "family_canonical",
                "type_slug",
                "sample_count",
                "support_ge_30_flag",
                "support_ge_50_flag",
                "benchmark_eligible_n_ge_3",
                "run_id",
            ]
        )
    grouped = support_df.rename(columns={"family_support": "sample_count"}).copy()
    grouped["support_ge_30_flag"] = (grouped["sample_count"] >= 30).astype(int)
    grouped["support_ge_50_flag"] = (grouped["sample_count"] >= 50).astype(int)
    grouped["run_id"] = run_id
    return grouped.sort_values("sample_count", ascending=False).reset_index(drop=True)


def _build_dangerous_distribution_by_type(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    if not isinstance(permission_rows_df, pd.DataFrame) or permission_rows_df.empty:
        return pd.DataFrame(
            columns=[
                "run_id",
                "type_slug",
                "sample_count",
                "dangerous_count_strict_mean",
                "dangerous_count_strict_median",
                "dangerous_count_inclusive_mean",
                "dangerous_count_inclusive_median",
                "dangerous_count_unknown_component_mean",
                "unknown_protection_rate",
                "total_perm_count_mean",
                "total_perm_count_median",
                "permission_source_aosp_rate",
                "permission_source_oem_rate",
                "permission_source_app_defined_rate",
                "permission_source_unknown_rate",
            ]
        )
    perm_df = permission_rows_df.copy()
    perm_df["is_dangerous"] = perm_df["protection_level"].str.contains("DANGEROUS", regex=False).astype(int)
    perm_df["is_unknown"] = perm_df["protection_level"].str.contains("UNKNOWN", regex=False).astype(int)
    perm_df["is_inclusive_dangerous"] = ((perm_df["is_dangerous"] == 1) | (perm_df["is_unknown"] == 1)).astype(int)
    sample_counts = (
        perm_df.groupby("sample_id")
        .agg(
            dangerous_count_strict=("is_dangerous", "sum"),
            dangerous_count_inclusive=("is_inclusive_dangerous", "sum"),
            unknown_protection_count=("is_unknown", "sum"),
            total_perm_count=("permission_string", "count"),
        )
        .reset_index()
    )
    sample_counts["unknown_protection_rate"] = (
        sample_counts["unknown_protection_count"] / sample_counts["total_perm_count"].replace(0, np.nan)
    ).fillna(0.0)
    source_df = perm_df.copy()
    source_df["src_aosp"] = source_df["permission_source"].str.contains("AOSP", regex=False, na=False).astype(int)
    source_df["src_oem"] = source_df["permission_source"].str.contains("OEM", regex=False, na=False).astype(int)
    source_df["src_app"] = source_df["permission_source"].str.contains("APP", regex=False, na=False).astype(int)
    source_df["src_unknown"] = (
        ~(source_df["src_aosp"].astype(bool) | source_df["src_oem"].astype(bool) | source_df["src_app"].astype(bool))
    ).astype(int)
    source_counts = (
        source_df.groupby("sample_id")
        .agg(
            src_aosp=("src_aosp", "sum"),
            src_oem=("src_oem", "sum"),
            src_app=("src_app", "sum"),
            src_unknown=("src_unknown", "sum"),
        )
        .reset_index()
    )
    source_counts = source_counts.merge(
        sample_counts[["sample_id", "total_perm_count"]],
        on="sample_id",
        how="left",
    )
    for col in ["src_aosp", "src_oem", "src_app", "src_unknown"]:
        source_counts[col] = source_counts[col] / source_counts["total_perm_count"].replace(0, np.nan)
    source_counts = source_counts.fillna(0.0)
    merged = sample_core_df[["sample_id", "type_slug"]].merge(sample_counts, on="sample_id", how="left")
    merged = merged.merge(source_counts[["sample_id", "src_aosp", "src_oem", "src_app", "src_unknown"]], on="sample_id", how="left")
    for col in [
        "dangerous_count_strict",
        "dangerous_count_inclusive",
        "unknown_protection_count",
        "total_perm_count",
        "unknown_protection_rate",
        "src_aosp",
        "src_oem",
        "src_app",
        "src_unknown",
    ]:
        merged[col] = pd.to_numeric(merged.get(col, 0), errors="coerce").fillna(0.0)

    rows: list[dict[str, Any]] = []
    for type_slug, group in merged.groupby("type_slug", dropna=False):
        strict = group["dangerous_count_strict"]
        inclusive = group["dangerous_count_inclusive"]
        total = group["total_perm_count"]
        rows.append(
            {
                "run_id": run_id,
                "type_slug": str(type_slug or "unknown"),
                "sample_count": int(len(group)),
                "dangerous_count_strict_mean": round(float(strict.mean()), 6),
                "dangerous_count_strict_median": round(float(strict.median()), 6),
                "dangerous_count_inclusive_mean": round(float(inclusive.mean()), 6),
                "dangerous_count_inclusive_median": round(float(inclusive.median()), 6),
                "dangerous_count_unknown_component_mean": round(float((inclusive - strict).mean()), 6),
                "unknown_protection_rate": round(float(group["unknown_protection_rate"].mean()), 6),
                "total_perm_count_mean": round(float(total.mean()), 6),
                "total_perm_count_median": round(float(total.median()), 6),
                "permission_source_aosp_rate": round(float(group["src_aosp"].mean()), 6),
                "permission_source_oem_rate": round(float(group["src_oem"].mean()), 6),
                "permission_source_app_defined_rate": round(float(group["src_app"].mean()), 6),
                "permission_source_unknown_rate": round(float(group["src_unknown"].mean()), 6),
            }
        )
    return pd.DataFrame(rows).sort_values("sample_count", ascending=False).reset_index(drop=True)


def _build_banker_permission_trends_over_time(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    """Build quarterly banker permission trends from VT temporal fields."""
    columns = [
        "run_id",
        "period_quarter",
        "year",
        "quarter",
        "sample_count",
        "banker_sample_count",
        "dangerous_count_strict_mean_all",
        "dangerous_count_strict_mean_banker",
        "banker_bind_accessibility_service_prevalence",
        "banker_system_alert_window_prevalence",
        "banker_request_install_packages_prevalence",
        "banker_read_sms_prevalence",
        "banker_receive_sms_prevalence",
        "banker_send_sms_prevalence",
    ]
    if sample_core_df.empty:
        return pd.DataFrame(columns=columns)
    core = sample_core_df.copy()
    core["time_anchor"] = pd.to_datetime(core.get("vt_first_seen_itw_date"), errors="coerce", utc=True)
    fallback = pd.to_datetime(core.get("vt_first_submission_at_utc"), errors="coerce", utc=True)
    core["time_anchor"] = core["time_anchor"].where(core["time_anchor"].notna(), fallback)
    core = core[core["time_anchor"].notna()].copy()
    if core.empty:
        return pd.DataFrame(columns=columns)
    core["year"] = core["time_anchor"].dt.year.astype(int)
    core["quarter"] = core["time_anchor"].dt.quarter.astype(int)
    core["period_quarter"] = core["year"].astype(str) + "-Q" + core["quarter"].astype(str)

    perm = permission_rows_df.copy() if isinstance(permission_rows_df, pd.DataFrame) else pd.DataFrame()
    if perm.empty:
        perm = pd.DataFrame(columns=["sample_id", "permission_string", "protection_level"])
    perm["is_dangerous"] = (
        perm.get("protection_level", "").astype(str).str.upper().str.contains("DANGEROUS", regex=False)
    ).astype(int)
    danger = perm.groupby("sample_id", as_index=False)["is_dangerous"].sum().rename(
        columns={"is_dangerous": "dangerous_count_strict"}
    )
    core = core.merge(danger, on="sample_id", how="left")
    core["dangerous_count_strict"] = pd.to_numeric(core["dangerous_count_strict"], errors="coerce").fillna(0.0)

    sensitive = {
        "android.permission.bind_accessibility_service": "banker_bind_accessibility_service_prevalence",
        "android.permission.system_alert_window": "banker_system_alert_window_prevalence",
        "android.permission.request_install_packages": "banker_request_install_packages_prevalence",
        "android.permission.read_sms": "banker_read_sms_prevalence",
        "android.permission.receive_sms": "banker_receive_sms_prevalence",
        "android.permission.send_sms": "banker_send_sms_prevalence",
    }
    flags = pd.DataFrame({"sample_id": core["sample_id"].astype(int)})
    for perm_name, out_col in sensitive.items():
        subset = perm[perm["permission_string"] == perm_name][["sample_id"]].drop_duplicates()
        subset[out_col] = 1
        flags = flags.merge(subset, on="sample_id", how="left")
        flags[out_col] = pd.to_numeric(flags[out_col], errors="coerce").fillna(0).astype(int)
    core = core.merge(flags, on="sample_id", how="left")

    rows: list[dict[str, Any]] = []
    for (year, quarter), group in core.groupby(["year", "quarter"], dropna=False):
        banker_group = group[group["type_slug"] == "banker"].copy()
        row: dict[str, Any] = {
            "run_id": run_id,
            "period_quarter": f"{int(year)}-Q{int(quarter)}",
            "year": int(year),
            "quarter": int(quarter),
            "sample_count": int(len(group)),
            "banker_sample_count": int(len(banker_group)),
            "dangerous_count_strict_mean_all": float(group["dangerous_count_strict"].mean()),
            "dangerous_count_strict_mean_banker": (
                float(banker_group["dangerous_count_strict"].mean()) if not banker_group.empty else np.nan
            ),
        }
        for out_col in sensitive.values():
            row[out_col] = float(banker_group[out_col].mean()) if not banker_group.empty else np.nan
        rows.append(row)
    out = pd.DataFrame(rows, columns=columns)
    if out.empty:
        return pd.DataFrame(columns=columns)
    out = out.sort_values(["year", "quarter"]).reset_index(drop=True)
    numeric_cols = [
        "dangerous_count_strict_mean_all",
        "dangerous_count_strict_mean_banker",
        "banker_bind_accessibility_service_prevalence",
        "banker_system_alert_window_prevalence",
        "banker_request_install_packages_prevalence",
        "banker_read_sms_prevalence",
        "banker_receive_sms_prevalence",
        "banker_send_sms_prevalence",
    ]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce").round(6)
    return out


def _build_banker_temporal_pattern_rows(
    temporal_trends_df: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    """Build a long-form normalized pattern view from banker temporal trend rows."""
    if not isinstance(temporal_trends_df, pd.DataFrame) or temporal_trends_df.empty:
        return pd.DataFrame(
            columns=[
                "run_id",
                "period_quarter",
                "year",
                "quarter",
                "type_slug",
                "permission",
                "banker_sample_count",
                "positive_count",
                "prevalence_pct",
                "pattern_score",
                "pattern_level",
                "pattern_label",
                "pattern_basis",
                "pattern_confidence",
                "pattern_reason",
            ]
        )
    metric_map = {
        "banker_bind_accessibility_service_prevalence": "android.permission.bind_accessibility_service",
        "banker_system_alert_window_prevalence": "android.permission.system_alert_window",
        "banker_request_install_packages_prevalence": "android.permission.request_install_packages",
        "banker_read_sms_prevalence": "android.permission.read_sms",
        "banker_receive_sms_prevalence": "android.permission.receive_sms",
        "banker_send_sms_prevalence": "android.permission.send_sms",
    }
    rows: list[dict[str, Any]] = []
    for _, row in temporal_trends_df.iterrows():
        support = safe_int_config_value(row.get("banker_sample_count", 0), default=0)
        for metric_col, permission_name in metric_map.items():
            prevalence = pd.to_numeric(row.get(metric_col), errors="coerce")
            if pd.isna(prevalence):
                continue
            prevalence_pct = float(prevalence) * 100.0
            positive_count = int(round(float(prevalence) * float(max(support, 0))))
            pattern_payload = _annotate_prevalence_patterns(
                pd.DataFrame(
                    [
                        {
                            "support": support,
                            "positive_count": positive_count,
                            "prevalence_pct": prevalence_pct,
                        }
                    ]
                ),
                support_col="support",
                positive_count_col="positive_count",
                prevalence_col="prevalence_pct",
                basis="banker_temporal_permission_trend",
            ).iloc[0].to_dict()
            rows.append(
                {
                    "run_id": run_id,
                    "period_quarter": str(row.get("period_quarter", "") or "").strip(),
                    "year": safe_int_config_value(row.get("year", 0), default=0),
                    "quarter": safe_int_config_value(row.get("quarter", 0), default=0),
                    "type_slug": "banker",
                    "permission": permission_name,
                    "banker_sample_count": support,
                    "positive_count": positive_count,
                    "prevalence_pct": round(prevalence_pct, 6),
                    "pattern_score": pattern_payload["pattern_score"],
                    "pattern_level": pattern_payload["pattern_level"],
                    "pattern_label": pattern_payload["pattern_label"],
                    "pattern_basis": pattern_payload["pattern_basis"],
                    "pattern_confidence": pattern_payload["pattern_confidence"],
                    "pattern_reason": pattern_payload["pattern_reason"],
                }
            )
    return pd.DataFrame(rows).sort_values(
        by=["year", "quarter", "pattern_level", "prevalence_pct", "permission"],
        ascending=[False, False, False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)

def _build_type_confusion_summary(
    sample_core_df: pd.DataFrame,
    model_results: dict[str, Any],
    run_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    predictions = model_results.get("prediction_metadata", {})
    true_labels = model_results.get("true_labels", {})
    if not isinstance(predictions, dict) or not isinstance(true_labels, dict):
        return (
            pd.DataFrame(
                [{"run_id": run_id, "error_type": "no_predictions", "count": 0}]
            ),
            pd.DataFrame(
                columns=["run_id", "sample_id", "true_family_id", "pred_family_id", "true_type_slug", "pred_type_slug"]
            ),
        )
    family_to_type = (
        sample_core_df[["family_id", "type_slug"]]
        .drop_duplicates("family_id")
        .set_index("family_id")["type_slug"]
        .to_dict()
    )
    detail_rows: list[dict[str, Any]] = []
    within = 0
    cross = 0
    for sample_id, meta in predictions.items():
        if not isinstance(meta, dict):
            continue
        true_family = str(true_labels.get(sample_id, "")).strip()
        pred_family = str(meta.get("decoded_label", "")).strip()
        if not true_family or not pred_family:
            continue
        if pred_family == true_family:
            continue
        try:
            true_type = str(family_to_type.get(int(true_family), "unknown"))
        except Exception:
            true_type = "unknown"
        try:
            pred_type = str(family_to_type.get(int(pred_family), "unknown"))
        except Exception:
            pred_type = "unknown"
        if true_type == pred_type:
            within += 1
        else:
            cross += 1
        detail_rows.append(
            {
                "run_id": str(run_id),
                "sample_id": str(sample_id),
                "true_family_id": true_family,
                "pred_family_id": pred_family,
                "true_type_slug": true_type,
                "pred_type_slug": pred_type,
            }
        )
    total = within + cross
    summary_df = pd.DataFrame(
        [
            {"run_id": run_id, "error_type": "within_type_error", "count": within},
            {"run_id": run_id, "error_type": "cross_type_error", "count": cross},
            {"run_id": run_id, "error_type": "total_error", "count": total},
            {
                "run_id": run_id,
                "error_type": "within_type_error_ratio",
                "count": round(within / total, 6) if total else 0.0,
            },
            {
                "run_id": run_id,
                "error_type": "cross_type_error_ratio",
                "count": round(cross / total, 6) if total else 0.0,
            },
        ]
    )
    detail_df = pd.DataFrame(detail_rows)
    return summary_df, detail_df

def _build_per_family_performance_spread(
    sample_core_df: pd.DataFrame,
    model_results: dict[str, Any],
    run_id: str,
) -> pd.DataFrame:
    pred_meta = model_results.get("prediction_metadata", {})
    true_labels = model_results.get("true_labels", {})
    if not isinstance(pred_meta, dict) or not isinstance(true_labels, dict):
        return pd.DataFrame(
            columns=[
                "run_id",
                "family_id",
                "support",
                "precision",
                "recall",
                "f1_score",
                "avg_confidence",
                "type_slug",
                "family_canonical",
            ]
        )
    family_lookup = (
        sample_core_df[["family_id", "family_canonical", "type_slug"]]
        .drop_duplicates("family_id")
        .set_index("family_id")
        .to_dict(orient="index")
    )

    rows: list[dict[str, Any]] = []
    all_families = sorted({str(v) for v in true_labels.values() if str(v).strip()})
    for family_id in all_families:
        tp = 0
        fp = 0
        fn = 0
        conf_values: list[float] = []
        for sid, true_value in true_labels.items():
            true_family = str(true_value).strip()
            pred_data = pred_meta.get(sid, {})
            pred_family = str(pred_data.get("decoded_label", "")).strip() if isinstance(pred_data, dict) else ""
            confidence = float(pred_data.get("confidence", 0.0)) if isinstance(pred_data, dict) else 0.0
            if pred_family == family_id and true_family == family_id:
                tp += 1
                conf_values.append(confidence)
            elif pred_family == family_id and true_family != family_id:
                fp += 1
            elif pred_family != family_id and true_family == family_id:
                fn += 1
                conf_values.append(confidence)
        support = tp + fn
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / support if support else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0
        family_key = _safe_int(family_id)
        family_info = family_lookup.get(family_key, {}) if family_key is not None else {}
        rows.append(
            {
                "run_id": run_id,
                "family_id": family_id,
                "support": int(support),
                "precision": round(float(precision), 6),
                "recall": round(float(recall), 6),
                "f1_score": round(float(f1), 6),
                "avg_confidence": round(sum(conf_values) / len(conf_values), 6) if conf_values else 0.0,
                "type_slug": str(family_info.get("type_slug", "unknown")),
                "family_canonical": str(family_info.get("family_canonical", "")),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["support", "f1_score"], ascending=[False, False]).reset_index(drop=True)


def _safe_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _build_type_permission_prevalence(
    sample_core_df: pd.DataFrame,
    permission_matrix_df: pd.DataFrame,
    run_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    merged = sample_core_df[["sample_id", "type_slug"]].merge(permission_matrix_df, on="sample_id", how="left").fillna(0)
    permission_cols = [c for c in merged.columns if c not in {"sample_id", "type_slug"}]
    rows: list[dict[str, Any]] = []
    entropy_rows: list[dict[str, Any]] = []
    for type_slug, group in merged.groupby("type_slug", dropna=False):
        n = max(len(group), 1)
        prevalences = []
        for permission in permission_cols:
            prev = float(pd.to_numeric(group[permission], errors="coerce").fillna(0).mean())
            prevalences.append(prev)
            rows.append(
                {
                    "run_id": run_id,
                    "type_slug": str(type_slug),
                    "permission": permission,
                    "prevalence": round(prev, 6),
                    "prevalence_pct": round(prev * 100.0, 6),
                    "positive_count": int(round(prev * float(len(group)))),
                    "sample_count": int(len(group)),
                }
            )
        entropy, eff_div = _prevalence_entropy(prevalences)
        entropy_rows.append(
            {
                "run_id": run_id,
                "type_slug": str(type_slug),
                "sample_count": int(n),
                "permission_entropy": round(entropy, 6),
                "effective_diversity": round(eff_div, 6),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = _annotate_prevalence_patterns(
            out,
            support_col="sample_count",
            positive_count_col="positive_count",
            prevalence_col="prevalence_pct",
            basis="type_permission_profile",
        )
    return out, pd.DataFrame(entropy_rows)


def _family_support_frame(
    sample_core_df: pd.DataFrame,
    *,
    benchmark_min_support: int = 3,
) -> pd.DataFrame:
    work = sample_core_df.copy()
    masks = family_tier_authority.build_family_tier_masks(work)
    work = work.assign(
        __family_target_eligible=masks["family_target_eligible"],
        __type_target_eligible=masks["type_target_eligible"],
    )
    work = work[work["__family_target_eligible"]].copy()
    if work.empty:
        return pd.DataFrame(
            columns=[
                "family_id",
                "family_canonical",
                "type_slug",
                "family_support",
                "benchmark_eligible_n_ge_3",
            ]
        )
    grouped = (
        work.groupby(["family_id", "family_canonical"], dropna=False)
        .agg(
            family_support=("sample_id", "nunique"),
            type_slug=("type_slug", lambda values: next((str(v).strip() for v in values if str(v).strip()), "unknown")),
        )
        .reset_index()
    )
    grouped["benchmark_eligible_n_ge_3"] = (
        pd.to_numeric(grouped["family_support"], errors="coerce").fillna(0).astype(int) >= int(benchmark_min_support)
    )
    return grouped.sort_values(
        by=["family_support", "family_canonical"],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def _build_permission_prevalence_by_type(
    sample_core_df: pd.DataFrame,
    permission_matrix_df: pd.DataFrame,
) -> pd.DataFrame:
    merged = sample_core_df[["sample_id", "type_slug"]].merge(permission_matrix_df, on="sample_id", how="left").fillna(0)
    permission_cols = [c for c in merged.columns if c not in {"sample_id", "type_slug"}]
    rows: list[dict[str, Any]] = []
    for type_slug, group in merged.groupby("type_slug", dropna=False):
        n_samples = int(len(group))
        for permission in permission_cols:
            present = pd.to_numeric(group[permission], errors="coerce").fillna(0)
            positive_count = int((present > 0).sum())
            rows.append(
                {
                    "type_slug": str(type_slug),
                    "permission": str(permission),
                    "n_samples": n_samples,
                    "permission_positive_count": positive_count,
                    "prevalence_pct": round((float(positive_count) / float(max(n_samples, 1))) * 100.0, 6),
                }
            )
    return _annotate_prevalence_patterns(
        pd.DataFrame(rows),
        support_col="n_samples",
        positive_count_col="permission_positive_count",
        basis="permission_prevalence_by_type",
    )


def _build_permission_prevalence_by_family(
    sample_core_df: pd.DataFrame,
    permission_matrix_df: pd.DataFrame,
    *,
    benchmark_min_support: int = 3,
) -> pd.DataFrame:
    family_support_df = _family_support_frame(sample_core_df, benchmark_min_support=benchmark_min_support)
    if family_support_df.empty:
        return pd.DataFrame(
            columns=[
                "family_canonical",
                "type_slug",
                "family_support",
                "permission",
                "positive_count",
                "prevalence_pct",
                "benchmark_eligible_n_ge_3",
            ]
        )
    merged = (
        sample_core_df[["sample_id", "family_id", "family_canonical"]]
        .merge(family_support_df, on=["family_id", "family_canonical"], how="inner")
        .merge(permission_matrix_df, on="sample_id", how="left")
        .fillna(0)
    )
    permission_cols = [c for c in permission_matrix_df.columns if c != "sample_id"]
    rows: list[dict[str, Any]] = []
    for (family_name, type_slug, family_support, benchmark_eligible), group in merged.groupby(
        ["family_canonical", "type_slug", "family_support", "benchmark_eligible_n_ge_3"],
        dropna=False,
    ):
        for permission in permission_cols:
            present = pd.to_numeric(group[permission], errors="coerce").fillna(0)
            positive_count = int((present > 0).sum())
            rows.append(
                {
                    "family_canonical": str(family_name),
                    "type_slug": str(type_slug),
                    "family_support": int(family_support),
                    "permission": str(permission),
                    "positive_count": positive_count,
                    "prevalence_pct": round((float(positive_count) / float(max(int(family_support), 1))) * 100.0, 6),
                    "benchmark_eligible_n_ge_3": bool(benchmark_eligible),
                }
            )
    out = pd.DataFrame(rows).sort_values(
        by=["family_support", "family_canonical", "prevalence_pct", "permission"],
        ascending=[False, True, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return _annotate_prevalence_patterns(
        out,
        support_col="family_support",
        basis="permission_prevalence_by_family",
    )


def _signal_catalog_frame() -> pd.DataFrame:
    rows = _load_permission_signal_catalog_rows()
    if not rows:
        rows = _SIGNAL_CATALOG_ROWS
    return pd.DataFrame(rows).copy()


def _signal_mapping_frame() -> pd.DataFrame:
    rows = _load_permission_signal_mapping_rows()
    if not rows:
        rows = _SIGNAL_MAPPING_ROWS
    return pd.DataFrame(rows).copy()


def _filter_behavior_safe_signals(signal_prevalence_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(signal_prevalence_df, pd.DataFrame) or signal_prevalence_df.empty:
        return pd.DataFrame(columns=getattr(signal_prevalence_df, "columns", []))
    return signal_prevalence_df[
        pd.to_numeric(signal_prevalence_df["include_in_behavioral_claims"], errors="coerce")
        .fillna(0)
        .astype(bool)
    ].copy()


def _build_permission_signal_governance_coverage(
    permission_rows_df: pd.DataFrame,
    permission_signal_rows_df: pd.DataFrame,
    *,
    run_id: str,
) -> pd.DataFrame:
    columns = ["run_id", "metric", "value"]
    if not isinstance(permission_rows_df, pd.DataFrame) or permission_rows_df.empty:
        return pd.DataFrame(columns=columns)
    work = permission_rows_df.copy()
    for col in (
        "effective_source_family_key",
        "candidate_source_family_key",
        "effective_review_lane",
        "effective_resolution_semantics",
    ):
        series = work[col] if col in work.columns else pd.Series("", index=work.index, dtype="object")
        work[col] = series.fillna("").astype(str).str.strip().str.lower()
    work["has_effective_lane"] = work["effective_source_family_key"].ne("")
    work["has_candidate_lane"] = work["candidate_source_family_key"].ne("")
    work["has_review_lane"] = work["effective_review_lane"].ne("")
    work["has_any_governance_lane"] = (
        work["has_effective_lane"] | work["has_candidate_lane"] | work["has_review_lane"]
    )
    unique_pairs = work.drop_duplicates(subset=["sample_id", "permission_string"]).copy()
    signal_pairs = (
        permission_signal_rows_df.drop_duplicates(subset=["sample_id", "signal_key"])
        if isinstance(permission_signal_rows_df, pd.DataFrame) and not permission_signal_rows_df.empty
        else pd.DataFrame(columns=["sample_id", "signal_key"])
    )
    rows = [
        {"run_id": run_id, "metric": "permission_row_count", "value": int(len(work))},
        {"run_id": run_id, "metric": "unique_sample_permission_pairs", "value": int(len(unique_pairs))},
        {"run_id": run_id, "metric": "rows_with_effective_lane", "value": int(work["has_effective_lane"].sum())},
        {"run_id": run_id, "metric": "rows_with_candidate_lane", "value": int(work["has_candidate_lane"].sum())},
        {"run_id": run_id, "metric": "rows_with_review_lane", "value": int(work["has_review_lane"].sum())},
        {"run_id": run_id, "metric": "rows_with_any_governance_lane", "value": int(work["has_any_governance_lane"].sum())},
        {"run_id": run_id, "metric": "unique_pairs_with_any_governance_lane", "value": int(unique_pairs["has_any_governance_lane"].sum())},
        {"run_id": run_id, "metric": "signal_assignment_pairs", "value": int(len(signal_pairs))},
    ]
    return pd.DataFrame(rows, columns=columns)


def _assign_permission_signal_keys(permission_rows_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(permission_rows_df, pd.DataFrame) or permission_rows_df.empty:
        return pd.DataFrame(columns=["sample_id", "signal_key"])
    work = permission_rows_df.copy()
    if "sample_id" not in work.columns or "permission_string" not in work.columns:
        return pd.DataFrame(columns=["sample_id", "signal_key"])
    work["sample_id"] = pd.to_numeric(work["sample_id"], errors="coerce")
    work = work.dropna(subset=["sample_id"]).copy()
    work["sample_id"] = work["sample_id"].astype(int)
    work["permission_string"] = work["permission_string"].fillna("").astype(str).str.strip().str.lower()
    work["permission_source"] = work.get("permission_source", "").fillna("").astype(str).str.upper()
    for col in ("effective_source_family_key", "candidate_source_family_key", "effective_review_lane"):
        series = work[col] if col in work.columns else pd.Series("", index=work.index, dtype="object")
        work[col] = series.fillna("").astype(str).str.strip().str.lower()
    work = work[work["permission_string"] != ""].copy()
    if work.empty:
        return pd.DataFrame(columns=["sample_id", "signal_key"])

    exact_map: dict[str, set[str]] = {}
    prefix_map: list[tuple[str, str]] = []
    remediation_lane_map: dict[str, set[str]] = {}
    for row in _load_permission_signal_mapping_rows() or _SIGNAL_MAPPING_ROWS:
        signal_key = str(row.get("signal_key", "")).strip()
        perm_name = str(row.get("perm_name", "")).strip().lower()
        basis = str(row.get("mapping_basis", "")).strip().lower()
        if not signal_key or not perm_name:
            continue
        if basis == "exact_permission":
            exact_map.setdefault(perm_name, set()).add(signal_key)
        elif basis == "prefix_pattern":
            prefix_map.append((perm_name, signal_key))
        elif basis == "remediation_lane":
            remediation_lane_map.setdefault(perm_name, set()).add(signal_key)

    rows: list[dict[str, Any]] = []
    dynamic_receiver_re = re.compile(r"\.dynamic_receiver_not_exported_permission[a-z0-9_]*$", re.IGNORECASE)
    legacy_push_re = re.compile(r"(?:\.permission)?\.c2d_message[a-z0-9_]*$", re.IGNORECASE)
    maps_receive_re = re.compile(r"\.permission\.maps_receive$", re.IGNORECASE)
    adm_re = re.compile(r"\.permission\.receive_adm_message$", re.IGNORECASE)
    apphub_re = re.compile(r"\.permission\.bind_apphub_service$", re.IGNORECASE)
    push_sdk_patterns = [
        re.compile(r"\.permission\.jpush_message$", re.IGNORECASE),
        re.compile(r"\.permission\.mipush_receive$", re.IGNORECASE),
        re.compile(r"\.permission\.push_provider$", re.IGNORECASE),
        re.compile(r"\.permission\.process_push_msg$", re.IGNORECASE),
        re.compile(r"getui\.permission\.getuiservice\.", re.IGNORECASE),
        re.compile(r"\.permission\.kubi_message$", re.IGNORECASE),
    ]
    launcher_patterns = [
        re.compile(r"com\.anddoes\.launcher\.permission\.update_count$", re.IGNORECASE),
        re.compile(r"com\.majeur\.launcher\.permission\.update_badge$", re.IGNORECASE),
        re.compile(r"me\.everything\.badger\.permission\.", re.IGNORECASE),
        re.compile(r"com\.android\.launcher[23]\.permission\.", re.IGNORECASE),
        re.compile(r"com\.google\.android\.launcher\.permission\.", re.IGNORECASE),
        re.compile(r"\.permission\.(?:read_settings|write_settings|receive_first_load_broadcast|receive_launch_broadcasts)$", re.IGNORECASE),
        re.compile(r"\.permission\.(?:install_shortcut|uninstall_shortcut)$", re.IGNORECASE),
        re.compile(r"\.permission\.(?:read_theme|receive_theme_update)$", re.IGNORECASE),
    ]
    lane_columns = [
        "sample_id",
        "permission_string",
        "permission_source",
        "effective_source_family_key",
        "candidate_source_family_key",
        "effective_review_lane",
    ]
    for row in work[lane_columns].drop_duplicates().to_dict(orient="records"):
        sample_id = int(row["sample_id"])
        perm = str(row["permission_string"]).strip().lower()
        source = str(row.get("permission_source", "")).strip().upper()
        effective_lane = str(row.get("effective_source_family_key", "")).strip().lower()
        candidate_lane = str(row.get("candidate_source_family_key", "")).strip().lower()
        review_lane = str(row.get("effective_review_lane", "")).strip().lower()
        signal_keys: set[str] = set()
        signal_keys.update(exact_map.get(perm, set()))
        for prefix, signal_key in prefix_map:
            if perm.startswith(prefix):
                signal_keys.add(signal_key)
        for lane_value in {effective_lane, candidate_lane, review_lane}:
            if lane_value:
                signal_keys.update(remediation_lane_map.get(lane_value, set()))
        if source == "GOOGLE":
            signal_keys.add("google_gms_ecosystem")
        elif source == "OEM":
            signal_keys.add("oem_vendor_ecosystem")
        elif source == "APP_DEFINED":
            if dynamic_receiver_re.search(perm):
                signal_keys.add("app_defined_scaffolding")
            elif legacy_push_re.search(perm):
                signal_keys.add("app_defined_scaffolding")
            elif maps_receive_re.search(perm):
                signal_keys.add("app_defined_scaffolding")
            elif adm_re.search(perm):
                signal_keys.add("app_defined_scaffolding")
            elif apphub_re.search(perm):
                signal_keys.add("app_defined_scaffolding")
            elif any(pattern.search(perm) for pattern in push_sdk_patterns):
                signal_keys.add("launcher_sdk_ecosystem_noise")
            elif any(pattern.search(perm) for pattern in launcher_patterns):
                signal_keys.add("launcher_sdk_ecosystem_noise")
        if not signal_keys:
            continue
        for signal_key in sorted(signal_keys):
            rows.append({"sample_id": sample_id, "signal_key": signal_key})
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["sample_id", "signal_key"])
    return out.drop_duplicates(subset=["sample_id", "signal_key"]).reset_index(drop=True)


def _build_signal_prevalence_by_type(
    sample_core_df: pd.DataFrame,
    permission_signal_rows_df: pd.DataFrame,
) -> pd.DataFrame:
    catalog_df = _signal_catalog_frame()
    merged = sample_core_df[["sample_id", "type_slug"]].copy()
    merged = merged.merge(permission_signal_rows_df, on="sample_id", how="left")
    rows: list[dict[str, Any]] = []
    for type_slug, group in merged.groupby("type_slug", dropna=False):
        n_samples = int(group["sample_id"].nunique())
        present_keys = (
            group.dropna(subset=["signal_key"])
            .groupby("signal_key")["sample_id"]
            .nunique()
            .to_dict()
        )
        for _, signal_row in catalog_df.iterrows():
            signal_key = str(signal_row["signal_key"])
            positive_count = int(present_keys.get(signal_key, 0))
            rows.append(
                {
                    "type_slug": str(type_slug),
                    "signal_key": signal_key,
                    "signal_label": str(signal_row["display_name"]),
                    "authority_lane": str(signal_row["authority_lane"]),
                    "include_in_model_features": bool(signal_row["include_in_model_features"]),
                    "include_in_behavioral_claims": bool(signal_row["include_in_behavioral_claims"]),
                    "type_sample_count": n_samples,
                    "positive_count": positive_count,
                    "prevalence_pct": round((float(positive_count) / float(max(n_samples, 1))) * 100.0, 6),
                }
            )
    return _annotate_prevalence_patterns(
        pd.DataFrame(rows),
        support_col="type_sample_count",
        basis="signal_prevalence_by_type",
    )


def _build_signal_prevalence_by_family(
    sample_core_df: pd.DataFrame,
    permission_signal_rows_df: pd.DataFrame,
    *,
    benchmark_min_support: int = 3,
) -> pd.DataFrame:
    family_support_df = _family_support_frame(sample_core_df, benchmark_min_support=benchmark_min_support)
    catalog_df = _signal_catalog_frame()
    if family_support_df.empty:
        return pd.DataFrame(
            columns=[
                "family_canonical",
                "type_slug",
                "family_support",
                "benchmark_eligible_n_ge_3",
                "signal_key",
                "signal_label",
                "authority_lane",
                "include_in_model_features",
                "include_in_behavioral_claims",
                "positive_count",
                "prevalence_pct",
            ]
        )
    merged = (
        sample_core_df[["sample_id", "family_id", "family_canonical"]]
        .merge(family_support_df, on=["family_id", "family_canonical"], how="inner")
        .merge(permission_signal_rows_df, on="sample_id", how="left")
    )
    rows: list[dict[str, Any]] = []
    for (family_name, type_slug, family_support, benchmark_eligible), group in merged.groupby(
        ["family_canonical", "type_slug", "family_support", "benchmark_eligible_n_ge_3"],
        dropna=False,
    ):
        present_keys = (
            group.dropna(subset=["signal_key"])
            .groupby("signal_key")["sample_id"]
            .nunique()
            .to_dict()
        )
        for _, signal_row in catalog_df.iterrows():
            signal_key = str(signal_row["signal_key"])
            positive_count = int(present_keys.get(signal_key, 0))
            rows.append(
                {
                    "family_canonical": str(family_name),
                    "type_slug": str(type_slug),
                    "family_support": int(family_support),
                    "benchmark_eligible_n_ge_3": bool(benchmark_eligible),
                    "signal_key": signal_key,
                    "signal_label": str(signal_row["display_name"]),
                    "authority_lane": str(signal_row["authority_lane"]),
                    "include_in_model_features": bool(signal_row["include_in_model_features"]),
                    "include_in_behavioral_claims": bool(signal_row["include_in_behavioral_claims"]),
                    "positive_count": positive_count,
                    "prevalence_pct": round((float(positive_count) / float(max(int(family_support), 1))) * 100.0, 6),
                }
            )
    out = pd.DataFrame(rows).sort_values(
        by=["family_support", "family_canonical", "signal_key"],
        ascending=[False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return _annotate_prevalence_patterns(
        out,
        support_col="family_support",
        basis="signal_prevalence_by_family",
    )


def _build_family_signal_similarity(
    family_signal_prevalence_df: pd.DataFrame,
) -> pd.DataFrame:
    if family_signal_prevalence_df.empty:
        return pd.DataFrame(
            columns=[
                "family_a",
                "family_b",
                "type_a",
                "type_b",
                "support_a",
                "support_b",
                "jaccard_similarity",
                "cosine_similarity",
                "spearman_correlation",
                "same_type_flag",
            ]
        )
    pivot = family_signal_prevalence_df.pivot_table(
        index=["family_canonical", "type_slug", "family_support"],
        columns="signal_key",
        values="prevalence_pct",
        fill_value=0.0,
    )
    index_rows = pivot.index.tolist()
    rows: list[dict[str, Any]] = []
    for i, left_key in enumerate(index_rows):
        left_vec = np.array(pivot.loc[left_key], dtype=float)
        for j in range(i + 1, len(index_rows)):
            right_key = index_rows[j]
            right_vec = np.array(pivot.loc[right_key], dtype=float)
            family_a, type_a, support_a = left_key
            family_b, type_b, support_b = right_key
            spearman = _spearman_similarity_details(left_vec, right_vec)
            rows.append(
                {
                    "family_a": str(family_a),
                    "family_b": str(family_b),
                    "type_a": str(type_a),
                    "type_b": str(type_b),
                    "support_a": int(support_a),
                    "support_b": int(support_b),
                    "jaccard_similarity": round(_jaccard_similarity(left_vec, right_vec), 6),
                    "cosine_similarity": round(_cosine_similarity(left_vec, right_vec), 6),
                    "spearman_correlation": (
                        round(float(spearman["spearman_correlation"]), 6)
                        if spearman["spearman_correlation"] is not None else None
                    ),
                    "correlation_status": spearman["correlation_status"],
                    "left_profile_constant": spearman["left_profile_constant"],
                    "right_profile_constant": spearman["right_profile_constant"],
                    "same_type_flag": bool(str(type_a) == str(type_b)),
                }
            )
    out = pd.DataFrame(rows).sort_values(
        by=["same_type_flag", "cosine_similarity", "jaccard_similarity", "family_a", "family_b"],
        ascending=[False, False, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return _annotate_similarity_patterns(
        out,
        support_a_col="support_a",
        support_b_col="support_b",
        same_type_col="same_type_flag",
        basis="family_signal_similarity",
    )


def _interpret_enrichment_bucket(odds_ratio: float, q_value: float) -> str:
    if not np.isfinite(float(odds_ratio)) or not np.isfinite(float(q_value)):
        return "no_signal"
    q = float(q_value)
    or_val = float(odds_ratio)
    if q < 0.05 and or_val >= 2.0:
        return "strong_enriched"
    if q < 0.05 and or_val >= 1.5:
        return "enriched"
    if q < 0.05 and or_val <= 0.5:
        return "strong_depleted"
    if q < 0.05 and or_val <= (1.0 / 1.5):
        return "depleted"
    return "no_signal"


def _build_permission_type_enrichment(
    sample_core_df: pd.DataFrame,
    permission_matrix_df: pd.DataFrame,
) -> pd.DataFrame:
    merged = sample_core_df[["sample_id", "type_slug"]].merge(permission_matrix_df, on="sample_id", how="left").fillna(0)
    permission_cols = [c for c in merged.columns if c not in {"sample_id", "type_slug"}]
    rows: list[dict[str, Any]] = []
    for type_slug, group in merged.groupby("type_slug", dropna=False):
        other = merged[merged["type_slug"] != type_slug]
        if group.empty or other.empty:
            continue
        n_type = int(len(group))
        n_other = int(len(other))
        for permission in permission_cols:
            present_type = pd.to_numeric(group[permission], errors="coerce").fillna(0).astype(int) > 0
            present_other = pd.to_numeric(other[permission], errors="coerce").fillna(0).astype(int) > 0
            a = int(present_type.sum())
            b = int(n_type - a)
            c = int(present_other.sum())
            d = int(n_other - c)
            odds_ratio = ((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5))
            p_value, _cramers_v = _chi2_2x2_p_and_v(a, b, c, d)
            rows.append(
                {
                    "permission": str(permission),
                    "type_slug": str(type_slug),
                    "type_sample_count": n_type,
                    "background_sample_count": n_other,
                    "type_prevalence_pct": round((float(a) / float(max(n_type, 1))) * 100.0, 6),
                    "non_type_prevalence_pct": round((float(c) / float(max(n_other, 1))) * 100.0, 6),
                    "odds_ratio": round(float(odds_ratio), 6),
                    "p_value": float(p_value),
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["q_value_fdr"] = _bh_fdr(out["p_value"].tolist())
    out["interpretation_bucket"] = out.apply(
        lambda row: _interpret_enrichment_bucket(
            float(row.get("odds_ratio", 1.0)),
            float(row.get("q_value_fdr", 1.0)),
        ),
        axis=1,
    )
    out = out.sort_values(
        by=["q_value_fdr", "odds_ratio", "type_slug", "permission"],
        ascending=[True, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return _annotate_enrichment_patterns(
        out,
        support_col="type_sample_count",
        subject_prevalence_col="type_prevalence_pct",
        background_prevalence_col="non_type_prevalence_pct",
        basis="type_enrichment_vs_rest",
    )


def _build_permission_family_enrichment(
    sample_core_df: pd.DataFrame,
    permission_matrix_df: pd.DataFrame,
    *,
    benchmark_min_support: int = 3,
) -> pd.DataFrame:
    family_support_df = _family_support_frame(sample_core_df, benchmark_min_support=benchmark_min_support)
    if family_support_df.empty:
        return pd.DataFrame(
            columns=[
                "permission",
                "family_canonical",
                "type_slug",
                "family_support",
                "family_prevalence_pct",
                "non_family_prevalence_pct",
                "odds_ratio",
                "p_value",
                "q_value_fdr",
                "benchmark_eligible_n_ge_3",
            ]
        )
    merged = (
        sample_core_df[["sample_id", "family_id", "family_canonical"]]
        .merge(family_support_df, on=["family_id", "family_canonical"], how="inner")
        .merge(permission_matrix_df, on="sample_id", how="left")
        .fillna(0)
    )
    permission_cols = [c for c in permission_matrix_df.columns if c != "sample_id"]
    rows: list[dict[str, Any]] = []
    for family_name, group in merged.groupby("family_canonical", dropna=False):
        other = merged[merged["family_canonical"] != family_name]
        if group.empty or other.empty:
            continue
        family_support = int(pd.to_numeric(group["family_support"], errors="coerce").fillna(0).iloc[0])
        type_slug = str(group["type_slug"].iloc[0])
        benchmark_eligible = bool(group["benchmark_eligible_n_ge_3"].iloc[0])
        for permission in permission_cols:
            present_family = pd.to_numeric(group[permission], errors="coerce").fillna(0).astype(int) > 0
            present_other = pd.to_numeric(other[permission], errors="coerce").fillna(0).astype(int) > 0
            a = int(present_family.sum())
            b = int(len(group) - a)
            c = int(present_other.sum())
            d = int(len(other) - c)
            odds_ratio = ((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5))
            p_value, _cramers_v = _chi2_2x2_p_and_v(a, b, c, d)
            rows.append(
                {
                    "permission": str(permission),
                    "family_canonical": str(family_name),
                    "type_slug": type_slug,
                    "family_support": family_support,
                    "family_prevalence_pct": round((float(a) / float(max(len(group), 1))) * 100.0, 6),
                    "non_family_prevalence_pct": round((float(c) / float(max(len(other), 1))) * 100.0, 6),
                    "odds_ratio": round(float(odds_ratio), 6),
                    "p_value": float(p_value),
                    "benchmark_eligible_n_ge_3": benchmark_eligible,
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["q_value_fdr"] = _bh_fdr(out["p_value"].tolist())
    out["interpretation_bucket"] = out.apply(
        lambda row: _interpret_enrichment_bucket(
            float(row.get("odds_ratio", 1.0)),
            float(row.get("q_value_fdr", 1.0)),
        ),
        axis=1,
    )
    out = out.sort_values(
        by=["q_value_fdr", "odds_ratio", "family_support", "family_canonical", "permission"],
        ascending=[True, False, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return _annotate_enrichment_patterns(
        out,
        support_col="family_support",
        subject_prevalence_col="family_prevalence_pct",
        background_prevalence_col="non_family_prevalence_pct",
        basis="family_enrichment_vs_rest",
    )


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))


def _spearman_similarity_details(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    """Return Spearman value plus explicit undefined-input provenance."""
    left_constant = bool(left.size and np.allclose(left, left[0], equal_nan=True))
    right_constant = bool(right.size and np.allclose(right, right[0], equal_nan=True))
    if left.shape == right.shape and np.allclose(left, right, equal_nan=True):
        return {"spearman_correlation": 1.0, "correlation_status": "identical_profile", "left_profile_constant": left_constant, "right_profile_constant": right_constant}
    if left_constant or right_constant:
        return {"spearman_correlation": None, "correlation_status": "constant_input", "left_profile_constant": left_constant, "right_profile_constant": right_constant}
    try:
        corr = pd.Series(left).corr(pd.Series(right), method="spearman")
        if pd.notna(corr):
            return {"spearman_correlation": float(corr), "correlation_status": "defined", "left_profile_constant": False, "right_profile_constant": False}
        return {"spearman_correlation": None, "correlation_status": "undefined", "left_profile_constant": left_constant, "right_profile_constant": right_constant}
    except Exception:
        return {"spearman_correlation": None, "correlation_status": "error", "left_profile_constant": left_constant, "right_profile_constant": right_constant}


def _spearman_similarity(left: np.ndarray, right: np.ndarray) -> float:
    """Compatibility wrapper; new report builders should retain details."""
    value = _spearman_similarity_details(left, right)["spearman_correlation"]
    return float(value) if value is not None else float("nan")


def _jaccard_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_set = set(np.flatnonzero(left > 0.0).tolist())
    right_set = set(np.flatnonzero(right > 0.0).tolist())
    union = left_set | right_set
    if not union:
        return 1.0
    return float(len(left_set & right_set) / float(len(union)))


def _build_family_permission_similarity(
    family_prevalence_df: pd.DataFrame,
) -> pd.DataFrame:
    if family_prevalence_df.empty:
        return pd.DataFrame(
            columns=[
                "family_a",
                "family_b",
                "type_a",
                "type_b",
                "support_a",
                "support_b",
                "jaccard_similarity",
                "cosine_similarity",
                "spearman_correlation",
                "same_type_flag",
            ]
        )
    pivot = family_prevalence_df.pivot_table(
        index=["family_canonical", "type_slug", "family_support"],
        columns="permission",
        values="prevalence_pct",
        fill_value=0.0,
    )
    index_rows = pivot.index.tolist()
    rows: list[dict[str, Any]] = []
    for i, left_key in enumerate(index_rows):
        left_vec = np.array(pivot.loc[left_key], dtype=float)
        for j in range(i + 1, len(index_rows)):
            right_key = index_rows[j]
            right_vec = np.array(pivot.loc[right_key], dtype=float)
            family_a, type_a, support_a = left_key
            family_b, type_b, support_b = right_key
            spearman = _spearman_similarity_details(left_vec, right_vec)
            rows.append(
                {
                    "family_a": str(family_a),
                    "family_b": str(family_b),
                    "type_a": str(type_a),
                    "type_b": str(type_b),
                    "support_a": int(support_a),
                    "support_b": int(support_b),
                    "jaccard_similarity": round(_jaccard_similarity(left_vec, right_vec), 6),
                    "cosine_similarity": round(_cosine_similarity(left_vec, right_vec), 6),
                    "spearman_correlation": (
                        round(float(spearman["spearman_correlation"]), 6)
                        if spearman["spearman_correlation"] is not None else None
                    ),
                    "correlation_status": spearman["correlation_status"],
                    "left_profile_constant": spearman["left_profile_constant"],
                    "right_profile_constant": spearman["right_profile_constant"],
                    "same_type_flag": bool(str(type_a) == str(type_b)),
                }
            )
    out = pd.DataFrame(rows).sort_values(
        by=["same_type_flag", "cosine_similarity", "jaccard_similarity", "family_a", "family_b"],
        ascending=[False, False, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return _annotate_similarity_patterns(
        out,
        support_a_col="support_a",
        support_b_col="support_b",
        same_type_col="same_type_flag",
        basis="family_permission_similarity",
    )


def _build_type_permission_similarity(
    type_prevalence_df: pd.DataFrame,
) -> pd.DataFrame:
    if type_prevalence_df.empty:
        return pd.DataFrame(
            columns=[
                "type_a",
                "type_b",
                "support_a",
                "support_b",
                "jaccard_similarity",
                "cosine_similarity",
                "spearman_correlation",
            ]
        )
    pivot = type_prevalence_df.pivot_table(
        index=["type_slug", "n_samples"],
        columns="permission",
        values="prevalence_pct",
        fill_value=0.0,
    )
    types = pivot.index.tolist()
    rows: list[dict[str, Any]] = []
    for i, left_key in enumerate(types):
        left_vec = np.array(pivot.loc[left_key], dtype=float)
        for j in range(i + 1, len(types)):
            right_key = types[j]
            right_vec = np.array(pivot.loc[right_key], dtype=float)
            type_a, support_a = left_key
            type_b, support_b = right_key
            spearman = _spearman_similarity_details(left_vec, right_vec)
            rows.append(
                {
                    "type_a": str(type_a),
                    "type_b": str(type_b),
                    "support_a": int(support_a),
                    "support_b": int(support_b),
                    "jaccard_similarity": round(_jaccard_similarity(left_vec, right_vec), 6),
                    "cosine_similarity": round(_cosine_similarity(left_vec, right_vec), 6),
                    "spearman_correlation": (
                        round(float(spearman["spearman_correlation"]), 6)
                        if spearman["spearman_correlation"] is not None else None
                    ),
                    "correlation_status": spearman["correlation_status"],
                    "left_profile_constant": spearman["left_profile_constant"],
                    "right_profile_constant": spearman["right_profile_constant"],
                }
            )
    out = pd.DataFrame(rows).sort_values(
        by=["cosine_similarity", "jaccard_similarity", "type_a", "type_b"],
        ascending=[False, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return _annotate_similarity_patterns(
        out,
        support_a_col="support_a",
        support_b_col="support_b",
        basis="type_permission_similarity",
    )


def _build_type_capability_bundle_prevalence(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    merged = sample_core_df[["sample_id", "type_slug"]].copy()
    if permission_rows_df.empty:
        return pd.DataFrame(
            columns=["run_id", "type_slug", "capability_bundle", "prevalence", "sample_count"]
        )
    work = permission_rows_df[["sample_id", "permission_string"]].copy()
    work["permission_string"] = work["permission_string"].fillna("").astype(str).str.strip().str.lower()
    work = work[work["permission_string"] != ""]
    if work.empty:
        return pd.DataFrame(
            columns=["run_id", "type_slug", "capability_bundle", "prevalence", "sample_count"]
        )
    rows: list[dict[str, Any]] = []
    for bundle_name, pattern in PERMISSION_GROUP_DEFINITIONS:
        matched = work[work["permission_string"].map(lambda value: bool(pattern.search(value)))]
        if matched.empty:
            continue
        bundle_df = matched[["sample_id"]].drop_duplicates().assign(bundle_name=bundle_name)
        bundle_merged = merged.merge(bundle_df, on="sample_id", how="left")
        bundle_merged["present"] = bundle_merged["bundle_name"].notna().astype(int)
        for type_slug, group in bundle_merged.groupby("type_slug", dropna=False):
            rows.append(
                {
                    "run_id": run_id,
                    "type_slug": str(type_slug),
                    "capability_bundle": str(bundle_name).replace("_count", ""),
                    "prevalence": round(float(group["present"].mean()), 6),
                    "prevalence_pct": round(float(group["present"].mean()) * 100.0, 6),
                    "positive_count": int(pd.to_numeric(group["present"], errors="coerce").fillna(0).sum()),
                    "sample_count": int(len(group)),
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return _annotate_prevalence_patterns(
        out,
        support_col="sample_count",
        positive_count_col="positive_count",
        prevalence_col="prevalence_pct",
        basis="capability_bundle_prevalence_by_type",
    )


def _build_family_capability_bundle_profiles(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    supports = _family_support_frame(sample_core_df, benchmark_min_support=3).rename(
        columns={"family_support": "sample_count"}
    )
    visual_families = _select_visual_families(sample_core_df=sample_core_df)
    visual_set = {str(name) for name in visual_families}
    keep = supports[supports["family_canonical"].astype(str).isin(visual_set)].copy()
    if keep.empty or permission_rows_df.empty:
        return pd.DataFrame(
            columns=[
                "run_id",
                "family_id",
                "family_canonical",
                "type_slug",
                "benchmark_eligible_n_ge_3",
                "capability_bundle",
                "prevalence",
                "sample_count",
            ]
        )
    merged = sample_core_df[["sample_id", "family_id", "family_canonical"]].merge(
        keep[["family_id", "family_canonical", "type_slug", "sample_count", "benchmark_eligible_n_ge_3"]],
        on=["family_id", "family_canonical"],
        how="inner",
    )[["sample_id", "family_id", "family_canonical", "type_slug", "sample_count", "benchmark_eligible_n_ge_3"]]
    work = permission_rows_df[["sample_id", "permission_string"]].copy()
    work["permission_string"] = work["permission_string"].fillna("").astype(str).str.strip().str.lower()
    work = work[work["permission_string"] != ""]
    rows: list[dict[str, Any]] = []
    for bundle_name, pattern in PERMISSION_GROUP_DEFINITIONS:
        matched = work[work["permission_string"].map(lambda value: bool(pattern.search(value)))]
        if matched.empty:
            continue
        bundle_df = matched[["sample_id"]].drop_duplicates().assign(bundle_name=bundle_name)
        bundle_merged = merged.merge(bundle_df, on="sample_id", how="left")
        bundle_merged["present"] = bundle_merged["bundle_name"].notna().astype(int)
        for (family_id, family_name, type_slug, sample_count, benchmark_eligible), group in bundle_merged.groupby(
            ["family_id", "family_canonical", "type_slug", "sample_count", "benchmark_eligible_n_ge_3"], dropna=False
        ):
            rows.append(
                {
                    "run_id": run_id,
                    "family_id": str(family_id),
                    "family_canonical": str(family_name),
                    "type_slug": str(type_slug),
                    "benchmark_eligible_n_ge_3": bool(benchmark_eligible),
                    "capability_bundle": str(bundle_name).replace("_count", ""),
                    "prevalence": round(float(group["present"].mean()), 6),
                    "prevalence_pct": round(float(group["present"].mean()) * 100.0, 6),
                    "positive_count": int(pd.to_numeric(group["present"], errors="coerce").fillna(0).sum()),
                    "sample_count": int(sample_count),
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(
        by=["sample_count", "family_canonical", "prevalence", "capability_bundle"],
        ascending=[False, True, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return _annotate_prevalence_patterns(
        out,
        support_col="sample_count",
        positive_count_col="positive_count",
        prevalence_col="prevalence_pct",
        basis="capability_bundle_prevalence_by_family",
    )


def _build_family_permission_profiles(
    sample_core_df: pd.DataFrame,
    permission_matrix_df: pd.DataFrame,
    run_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    supports = _family_support_frame(sample_core_df, benchmark_min_support=3).rename(
        columns={"family_support": "sample_count"}
    )
    visual_families = _select_visual_families(sample_core_df=sample_core_df)
    visual_set = {str(name) for name in visual_families}
    main = supports[supports["family_canonical"].astype(str).isin(visual_set)].copy()
    if not main.empty:
        visual_rank = {name: idx for idx, name in enumerate(visual_families)}
        main["__rank"] = main["family_canonical"].astype(str).map(visual_rank).fillna(10_000).astype(int)
        main = main.sort_values(by=["__rank", "family_canonical"], ascending=[True, True], kind="mergesort")
        main = main.drop(columns=["__rank"])
    appendix = (
        supports[supports["sample_count"] >= 30]
        .sort_values(by=["sample_count", "family_canonical"], ascending=[False, True], kind="mergesort")
        .head(20)
    )
    if not main.empty and not appendix.empty:
        appendix = appendix[~appendix["family_canonical"].astype(str).isin(main["family_canonical"].astype(str))].copy()
    keep = pd.concat([main.assign(profile_scope="main"), appendix.assign(profile_scope="appendix")], ignore_index=True)
    if keep.empty:
        return pd.DataFrame(), pd.DataFrame()
    merged = sample_core_df[["sample_id", "family_id", "family_canonical"]].merge(
        keep[["family_id", "family_canonical", "type_slug", "benchmark_eligible_n_ge_3", "profile_scope"]],
        on=["family_id", "family_canonical"],
        how="inner",
    ).merge(permission_matrix_df, on="sample_id", how="left")
    permission_cols = [c for c in permission_matrix_df.columns if c != "sample_id"]
    if permission_cols:
        merged[permission_cols] = merged[permission_cols].fillna(0)
    rows: list[dict[str, Any]] = []
    entropy_rows: list[dict[str, Any]] = []
    for (family_id, family_name, type_slug, benchmark_eligible, scope), group in merged.groupby(
        ["family_id", "family_canonical", "type_slug", "benchmark_eligible_n_ge_3", "profile_scope"], dropna=False
    ):
        prevalences = []
        for permission in permission_cols:
            prev = float(pd.to_numeric(group[permission], errors="coerce").fillna(0).mean())
            prevalences.append(prev)
            rows.append(
                {
                    "run_id": run_id,
                    "family_id": int(family_id),
                    "family_canonical": str(family_name),
                    "type_slug": str(type_slug),
                    "benchmark_eligible_n_ge_3": bool(benchmark_eligible),
                    "profile_scope": str(scope),
                    "permission": permission,
                    "prevalence": round(prev, 6),
                    "prevalence_pct": round(prev * 100.0, 6),
                    "positive_count": int(round(prev * float(len(group)))),
                    "sample_count": int(len(group)),
                }
            )
        entropy, eff_div = _prevalence_entropy(prevalences)
        entropy_rows.append(
            {
                    "run_id": run_id,
                    "family_id": int(family_id),
                    "family_canonical": str(family_name),
                    "type_slug": str(type_slug),
                    "benchmark_eligible_n_ge_3": bool(benchmark_eligible),
                    "profile_scope": str(scope),
                    "sample_count": int(len(group)),
                    "permission_entropy": round(entropy, 6),
                    "effective_diversity": round(eff_div, 6),
                }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = _annotate_prevalence_patterns(
            out,
            support_col="sample_count",
            positive_count_col="positive_count",
            prevalence_col="prevalence_pct",
            basis="family_permission_profile",
        )
    return out, pd.DataFrame(entropy_rows)










def _build_banker_permission_enrichment(
    sample_core_df: pd.DataFrame,
    permission_matrix_df: pd.DataFrame,
    run_id: str,
    forced_permissions: set[str],
) -> pd.DataFrame:
    merged = sample_core_df[["sample_id", "type_slug"]].merge(permission_matrix_df, on="sample_id", how="left").fillna(0)
    permission_cols = [c for c in merged.columns if c not in {"sample_id", "type_slug"}]
    if not permission_cols:
        return pd.DataFrame()
    banker = merged["type_slug"].eq("banker")
    rows: list[dict[str, Any]] = []
    for permission in permission_cols:
        present = pd.to_numeric(merged[permission], errors="coerce").fillna(0).astype(int) > 0
        a = int((banker & present).sum())
        b = int((banker & (~present)).sum())
        c = int(((~banker) & present).sum())
        d = int(((~banker) & (~present)).sum())
        odds_ratio = ((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5))
        se = np.sqrt((1 / (a + 0.5)) + (1 / (b + 0.5)) + (1 / (c + 0.5)) + (1 / (d + 0.5)))
        ci_low = float(np.exp(np.log(odds_ratio) - 1.96 * se))
        ci_high = float(np.exp(np.log(odds_ratio) + 1.96 * se))
        p_value, cramers_v = _chi2_2x2_p_and_v(a, b, c, d)
        rows.append(
            {
                "run_id": run_id,
                "permission": permission,
                "banker_with_perm": a,
                "banker_without_perm": b,
                "non_banker_with_perm": c,
                "non_banker_without_perm": d,
                "odds_ratio": round(float(odds_ratio), 6),
                "odds_ratio_ci_low": round(ci_low, 6),
                "odds_ratio_ci_high": round(ci_high, 6),
                "p_value": p_value,
                "cramers_v": cramers_v,
                "forced_permission_flag": int(permission in forced_permissions),
            }
        )
    out = pd.DataFrame(rows)
    out["p_value_fdr_bh"] = _bh_fdr(out["p_value"].tolist())
    return out.sort_values(["odds_ratio", "banker_with_perm"], ascending=[False, False]).reset_index(drop=True)






def _build_permission_discriminability_rank(
    sample_core_df: pd.DataFrame,
    permission_matrix_df: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    return _build_permission_discriminability_rank_impl(sample_core_df, permission_matrix_df, run_id)


def _build_generic_vs_non_generic_summary(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
    permission_matrix_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    metrics_df = _build_sample_level_permission_metrics(sample_core_df, permission_rows_df)
    min_vendor_count = safe_int_config_value(
        getattr(app_config, "CONSENSUS_MIN_VENDOR_COUNT", 5),
        default=5,
    )
    consensus_keep = consensus_df[consensus_df["vendor_count"] >= min_vendor_count][
        ["sample_id", "consensus_score_all_vendors"]
    ].copy()
    base_cols = [
        "sample_id",
        "family_id",
        "family_canonical",
        "type_slug",
        "category_primary",
        "category_subtype",
        "sample_label_kind",
    ]
    present_cols = [col for col in base_cols if col in sample_core_df.columns]
    merged = sample_core_df[present_cols].merge(metrics_df, on="sample_id", how="left")
    merged = merged.merge(consensus_keep, on="sample_id", how="left")
    tier_masks = family_tier_authority.build_family_tier_masks(merged)
    merged["authority_tier"] = "non_generic"
    merged.loc[tier_masks["generic_coarse"], "authority_tier"] = "generic_or_coarse"
    merged.loc[tier_masks["unresolved"], "authority_tier"] = "unresolved"
    merged["permission_entropy"] = pd.to_numeric(merged.get("permission_entropy", 0.0), errors="coerce").fillna(0.0)
    merged["dangerous_count_strict"] = pd.to_numeric(merged.get("dangerous_count_strict", 0.0), errors="coerce").fillna(0.0)
    merged["dangerous_count_inclusive"] = pd.to_numeric(merged.get("dangerous_count_inclusive", 0.0), errors="coerce").fillna(0.0)
    merged["consensus_score_all_vendors"] = pd.to_numeric(
        merged.get("consensus_score_all_vendors", np.nan), errors="coerce"
    )

    rows: list[dict[str, Any]] = []
    for tag, group in merged.groupby("authority_tier", dropna=False):
        rows.append(
            {
                "run_id": run_id,
                "group": str(tag),
                "sample_count": int(len(group)),
                "permission_entropy_mean": round(float(group["permission_entropy"].mean()), 6),
                "permission_entropy_median": round(float(group["permission_entropy"].median()), 6),
                "dangerous_count_strict_mean": round(float(group["dangerous_count_strict"].mean()), 6),
                "dangerous_count_strict_median": round(float(group["dangerous_count_strict"].median()), 6),
                "dangerous_count_inclusive_mean": round(float(group["dangerous_count_inclusive"].mean()), 6),
                "dangerous_count_inclusive_median": round(float(group["dangerous_count_inclusive"].median()), 6),
                "consensus_score_mean": round(_safe_series_mean(group["consensus_score_all_vendors"]), 6),
                "consensus_score_median": round(_safe_series_median(group["consensus_score_all_vendors"]), 6),
            }
        )
    generic_values = merged[merged["authority_tier"] == "generic_or_coarse"]
    non_generic_values = merged[merged["authority_tier"] == "non_generic"]
    if not generic_values.empty and not non_generic_values.empty:
        rows.append(
            {
                "run_id": run_id,
                "group": "effect_size",
                "sample_count": int(len(merged)),
                "permission_entropy_mean": round(
                    _cliffs_delta(generic_values["permission_entropy"], non_generic_values["permission_entropy"]), 6
                ),
                "permission_entropy_median": np.nan,
                "dangerous_count_strict_mean": round(
                    _cliffs_delta(generic_values["dangerous_count_strict"], non_generic_values["dangerous_count_strict"]), 6
                ),
                "dangerous_count_strict_median": np.nan,
                "dangerous_count_inclusive_mean": round(
                    _cliffs_delta(generic_values["dangerous_count_inclusive"], non_generic_values["dangerous_count_inclusive"]), 6
                ),
                "dangerous_count_inclusive_median": np.nan,
                "consensus_score_mean": round(
                    _cliffs_delta(
                        generic_values["consensus_score_all_vendors"].dropna(),
                        non_generic_values["consensus_score_all_vendors"].dropna(),
                    ),
                    6,
                ),
                "consensus_score_median": np.nan,
            }
        )
    return pd.DataFrame(rows)


def _build_sample_level_permission_metrics(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
) -> pd.DataFrame:
    return _build_sample_level_permission_metrics_impl(sample_core_df, permission_rows_df)



def _build_consensus_correlation_report(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    run_id: str,
) -> tuple[pd.DataFrame, str]:
    return _build_consensus_correlation_report_impl(
        sample_core_df,
        permission_rows_df,
        consensus_df,
        run_id,
        spearman_with_bootstrap_ci=_spearman_with_bootstrap_ci,
    )



def _build_dangerous_stats_tests(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    return _build_dangerous_stats_tests_impl(sample_core_df, permission_rows_df, run_id)


def _build_banker_family_pattern_clusters(
    sample_core_df: pd.DataFrame,
    family_profiles_df: pd.DataFrame,
    run_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if family_profiles_df.empty:
        empty = pd.DataFrame(columns=["run_id", "family_id", "family_canonical", "sample_count", "cluster_id"])
        return empty, pd.DataFrame(columns=["run_id", "cluster_id", "permission", "mean_prevalence"])
    banker_ids = (
        sample_core_df[sample_core_df["type_slug"] == "banker"]["family_id"].dropna().astype(int).unique().tolist()
    )
    subset = family_profiles_df[family_profiles_df["family_id"].isin(banker_ids)].copy()
    subset = subset[pd.to_numeric(subset["sample_count"], errors="coerce").fillna(0).astype(int) >= 30]
    if subset.empty:
        empty = pd.DataFrame(columns=["run_id", "family_id", "family_canonical", "sample_count", "cluster_id"])
        return empty, pd.DataFrame(columns=["run_id", "cluster_id", "permission", "mean_prevalence"])
    subset["scope_rank"] = subset["profile_scope"].map({"main": 0, "appendix": 1}).fillna(2)
    subset = subset.sort_values(["family_id", "permission", "scope_rank"]).drop_duplicates(
        subset=["family_id", "permission"], keep="first"
    )
    pivot = subset.pivot_table(
        index=["family_id", "family_canonical", "sample_count"],
        columns="permission",
        values="prevalence",
        fill_value=0.0,
    )
    if pivot.empty:
        empty = pd.DataFrame(columns=["run_id", "family_id", "family_canonical", "sample_count", "cluster_id"])
        return empty, pd.DataFrame(columns=["run_id", "cluster_id", "permission", "mean_prevalence"])
    n = len(pivot)
    requested_k = safe_int_config_value(
        getattr(app_config, "BANKER_PATTERN_CLUSTER_K", 3),
        default=3,
    )
    k = max(1, min(requested_k, n))
    if n == 1 or k == 1:
        labels = np.zeros(n, dtype=int)
    else:
        dist = np.zeros((n, n), dtype=float)
        matrix = pivot.values.astype(float)
        for i in range(n):
            p = matrix[i]
            p = p / p.sum() if p.sum() > 0 else np.ones_like(p) / max(len(p), 1)
            for j in range(i, n):
                q = matrix[j]
                q = q / q.sum() if q.sum() > 0 else np.ones_like(q) / max(len(q), 1)
                d = _js_distance(p, q)
                dist[i, j] = d
                dist[j, i] = d
        try:
            from sklearn.cluster import AgglomerativeClustering

            try:
                model = AgglomerativeClustering(n_clusters=k, metric="precomputed", linkage="average")
            except TypeError:
                model = AgglomerativeClustering(n_clusters=k, affinity="precomputed", linkage="average")
            labels = model.fit_predict(dist)
        except Exception:
            labels = np.arange(n) % k
    assignment_rows: list[dict[str, Any]] = []
    for idx, (family_id, family_name, sample_count) in enumerate(pivot.index.tolist()):
        assignment_rows.append(
            {
                "run_id": run_id,
                "family_id": int(family_id),
                "family_canonical": str(family_name),
                "sample_count": int(sample_count),
                "cluster_id": int(labels[idx]),
            }
        )
    assignments_df = pd.DataFrame(assignment_rows)
    profile_rows: list[dict[str, Any]] = []
    for cluster_id, fam_group in assignments_df.groupby("cluster_id", dropna=False):
        fam_ids = set(fam_group["family_id"].astype(int).tolist())
        cluster_subset = subset[subset["family_id"].isin(fam_ids)].copy()
        means = (
            cluster_subset.groupby("permission")["prevalence"]
            .mean()
            .sort_values(ascending=False)
            .head(15)
        )
        for permission, mean_val in means.items():
            profile_rows.append(
                {
                    "run_id": run_id,
                    "cluster_id": int(cluster_id),
                    "permission": str(permission),
                    "mean_prevalence": round(float(mean_val), 6),
                    "family_count": int(len(fam_ids)),
                }
            )
    profiles_df = pd.DataFrame(profile_rows)
    return assignments_df.sort_values(["cluster_id", "sample_count"], ascending=[True, False]), profiles_df


def _build_bundle_metadata(
    run_id: str,
    profile_id: str,
    sample_core_df: pd.DataFrame,
    coverage_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    family_support_df: pd.DataFrame,
    selected_vendors: list[str],
    engine_included_count: int,
    engine_excluded_count: int,
    permission_support_floor: int,
    kept_permission_count: int,
    kept_permissions_by_view: dict[str, list[str]],
    analysis_scope: str,
    figure_mode: str,
    cohort_hash: str,
    permission_feature_hash: str,
    type_heatmap_identity: str,
    dataset_time_contract: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
    min_selected = safe_int_config_value(
        getattr(app_config, "FEATURE_MIN_SELECTED_VENDORS", 1),
        default=1,
    )
    vendor_constrained = len(selected_vendors) < min_selected
    snapshot_meta = {
        "selection_rule_version": str(
            getattr(app_config, "ANALYSIS_SELECTION_RULE_VERSION", "snapshot_v1")
        ),
        "min_support": safe_int_config_value(getattr(app_config, "GENERIC_MIN_SUPPORT", 30), default=30),
        "permission_global_support_floor_rule": "max(50,1%)",
    }
    snapshot_meta.update(_read_snapshot_meta())
    excluded_low_vendor = int(
        pd.to_numeric(consensus_df.get("low_vendor_count_flag", 0), errors="coerce").fillna(0).sum()
    ) if isinstance(consensus_df, pd.DataFrame) and not consensus_df.empty else 0
    temporal_summary = _build_temporal_summary(sample_core_df)
    attack_mapping = _mobile_attack_permission_mapping_payload()
    return {
        "run_id": run_id,
        "profile_id": profile_id,
        "bundle_contract_name": BUNDLE_CONTRACT_NAME,
        "bundle_contract_version": BUNDLE_CONTRACT_VERSION,
        "code_commit_hash": run_manifest.get_git_commit(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_vendor_count": len(selected_vendors),
        "selected_vendors": selected_vendors,
        "vendor_constrained_run_flag": vendor_constrained,
        "engine_included_count": engine_included_count,
        "engine_excluded_count": engine_excluded_count,
        "feature_top_k": safe_int_config_value(getattr(app_config, "FEATURE_TOP_K", 8), default=8),
        "consensus_formula_version": "v1_top_vote_share_normalized_entropy",
        "consensus_min_vendor_count": safe_int_config_value(
            getattr(app_config, "CONSENSUS_MIN_VENDOR_COUNT", 5),
            default=5,
        ),
        "consensus_bootstrap_resamples": safe_int_config_value(
            getattr(app_config, "CONSENSUS_BOOTSTRAP_RESAMPLES", 2000),
            default=2000,
        ),
        "banker_pattern_cluster_k": safe_int_config_value(
            getattr(app_config, "BANKER_PATTERN_CLUSTER_K", 3),
            default=3,
        ),
        "permission_support_floor": int(permission_support_floor),
        "kept_permission_count": int(kept_permission_count),
        "permission_pattern_policy": {
            "primary_view": PRIMARY_PERMISSION_VIEW,
            "views": ["inclusive", "aosp_only", "ecosystem"],
            "permission_alias_map_version": PERMISSION_ALIAS_MAP_VERSION,
            "capability_bundle_names": [
                str(name).replace("_count", "") for name, _pattern in PERMISSION_GROUP_DEFINITIONS
            ],
            "capability_bundle_rule_count": int(len(PERMISSION_GROUP_DEFINITIONS)),
            "attack_mobile_mapping_version": str(attack_mapping.get("version", "") or "").strip(),
            "attack_mobile_mapping_hash": str(attack_mapping.get("hash", "") or "").strip(),
        },
        "analysis_scope": str(analysis_scope),
        "figure_mode": str(figure_mode),
        "cohort_hash": str(cohort_hash),
        "permission_feature_hash": str(permission_feature_hash),
        "type_permission_heatmap_identity": str(type_heatmap_identity),
        "kept_permission_count_by_view": {
            key: int(len(value)) for key, value in kept_permissions_by_view.items()
        },
        "snapshot_contract": snapshot_meta,
        "dataset_time_contract": dataset_time_contract or {},
        "coverage": coverage_df.to_dict(orient="records")[0] if not coverage_df.empty else {},
        "consensus_rows": int(len(consensus_df)),
        "consensus_excluded_low_vendor_count": excluded_low_vendor,
        "temporal_coverage": temporal_summary,
        "families_ge_50_support": int((family_support_df["support_ge_50_flag"] == 1).sum())
        if not family_support_df.empty
        else 0,
        "families_ge_30_support": int((family_support_df["support_ge_30_flag"] == 1).sum())
        if not family_support_df.empty
        else 0,
    }


def _build_temporal_summary(sample_core_df: pd.DataFrame) -> dict[str, Any]:
    """Summarize temporal coverage for snapshot using VT first-seen/submission fields."""
    if not isinstance(sample_core_df, pd.DataFrame) or sample_core_df.empty:
        return {}
    anchor = pd.to_datetime(sample_core_df.get("vt_first_seen_itw_date"), errors="coerce", utc=True)
    fallback = pd.to_datetime(sample_core_df.get("vt_first_submission_at_utc"), errors="coerce", utc=True)
    anchor = anchor.where(anchor.notna(), fallback)
    valid = anchor.dropna()
    if valid.empty:
        return {
            "samples_with_temporal_anchor": 0,
            "temporal_anchor_coverage": 0.0,
            "min_year": None,
            "max_year": None,
        }
    return {
        "samples_with_temporal_anchor": int(len(valid)),
        "temporal_anchor_coverage": round(float(len(valid) / max(len(sample_core_df), 1)), 6),
        "min_year": int(valid.dt.year.min()),
        "max_year": int(valid.dt.year.max()),
    }


def _select_banker_summary_rows(banker_enrichment_df: pd.DataFrame, limit: int) -> pd.DataFrame:
    if banker_enrichment_df.empty:
        return banker_enrichment_df
    work = banker_enrichment_df.copy()
    work["forced_permission_flag"] = pd.to_numeric(
        work.get("forced_permission_flag", 0), errors="coerce"
    ).fillna(0).astype(int)
    # Prefer the locked banker-sensitive permission set for narrative stability.
    forced = work[work["forced_permission_flag"] == 1].sort_values("odds_ratio", ascending=False)
    selected = forced.head(limit).copy()
    if len(selected) < limit:
        remaining = work[~work["permission"].isin(set(selected["permission"].tolist()))].sort_values(
            "odds_ratio",
            ascending=False,
        )
        fill = remaining.head(limit - len(selected))
        selected = pd.concat([selected, fill], ignore_index=True)
    return selected.head(limit).reset_index(drop=True)
