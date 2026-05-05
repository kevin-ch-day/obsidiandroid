"""Permission trends and classification pattern reporting stage."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from math import log
from pathlib import Path
import shutil
from typing import Any
import zipfile

import numpy as np
import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import output_paths
import obsidiandroid.governance.run_manifest as run_manifest
from analysis.pipeline.stage_results_warehouse import persist_permission_trends_results
from analysis.pipeline.permission_trends_selection import (
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

from analysis.pipeline.permission_trends.bundle_manifest import (
    export_permission_trends_bundle_manifest as _export_permission_trends_bundle_manifest,
    export_permission_trends_table_inventory_from_manifest as _export_permission_trends_table_inventory_from_manifest,
    resolve_bundle_artifact_dir as _resolve_bundle_artifact_dir,
)
from analysis.pipeline.permission_trends.publish_paths import (
    compute_cohort_hash as _compute_cohort_hash,
    compute_permission_feature_hash as _compute_permission_feature_hash,
    prune_run_stamped_pngs_in_latest_bundle as _prune_run_stamped_pngs_in_latest_bundle,
    publish_canonical_type_heatmap as _publish_canonical_type_heatmap,
    resolve_run_root_for_run_id as _resolve_run_root_for_run_id,
)
from analysis.pipeline.permission_trends.reporting_support import (
    compact_permission_label as _compact_permission_label,
    handle_reporting_exception as _handle_reporting_exception,
    read_dataset_time_contract as _read_dataset_time_contract,
    read_snapshot_meta as _read_snapshot_meta,
    write_run_scoped_permission_artifacts as _write_run_scoped_permission_artifacts,
)
from analysis.pipeline.permission_trends.constants import (
    ARTIFACT_GROUP_CONTRACTS,
    ARTIFACT_GROUP_DOCS,
    ARTIFACT_GROUP_FIGURES,
    ARTIFACT_GROUP_TABLES,
    BUNDLE_CONTRACT_NAME,
    BUNDLE_CONTRACT_VERSION,
    PERMISSION_ALIAS_MAP,
    PERMISSION_ALIAS_MAP_VERSION,
    PRIMARY_PERMISSION_VIEW,
    ReportArtifacts,
    RUN_SUFFIX_PNG_PATTERN,
)
from analysis.pipeline.permission_trends.sample_permission_data import (
    attach_temporal_catalog_fields as _attach_temporal_catalog_fields,
    build_permission_binary_matrix as _build_permission_binary_matrix,
    build_sample_core as _build_sample_core,
    fetch_permission_aggregates as _fetch_permission_aggregates,
    fetch_permission_rows_for_samples as _fetch_permission_rows_for_samples,
    fill_permission_observations as _fill_permission_observations,
    filter_permission_rows_by_view as _filter_permission_rows_by_view,
    permission_support_floor as _permission_support_floor,
)
from analysis.pipeline.permission_trends.stats_core import (
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


def _import_pyplot():
    """Import matplotlib pyplot with a headless-safe backend."""
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    return plt


def _report_figure_dpi() -> int:
    """Return figure export DPI for the current runtime mode."""
    if bool(getattr(app_config, "PAPER_MODE_ENABLED", False)):
        return 300
    return 180


def _spearman_with_bootstrap_ci(
    x: pd.Series, y: pd.Series
) -> tuple[float, float, float, float]:
    return _spearman_with_bootstrap_ci_impl(
        x,
        y,
        bootstrap_resamples=int(getattr(app_config, "CONSENSUS_BOOTSTRAP_RESAMPLES", 2000)),
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
    permission_rows_df = _fetch_permission_rows_for_samples(sample_core_df["sample_id"].tolist())
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
    type_entropy_csv = _export_df_with_latest(
        type_entropy_df,
        run_id=run_id,
        file_stem="type_permission_entropy",
        bundle_dir=bundle_dir,
    )
    type_heatmap_source_df = _filter_type_prevalence_for_visuals(type_prevalence_df)
    type_selected_permissions = _select_permissions_for_type_heatmap(
        method=str(getattr(app_config, "PERMISSION_SELECTION_METHOD", "discriminability")),
        top_k=int(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 30)),
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
            top_k=int(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 30)),
            selected_permissions=type_selected_permissions,
            title="Type permission heatmap",
        )
        if include_type_figures
        else None
    )
    paper_variant_paths: list[str] = []
    top_permissions_visual = int(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 30))
    top_families_visual = int(getattr(app_config, "MAX_FAMILY_VISUAL_COUNT", 12))
    canonical_heatmap_paths = _publish_canonical_type_heatmap(
        source_path=type_heatmap_png,
        run_id=run_id,
        cohort_hash=cohort_hash,
        permission_feature_hash=permission_feature_hash,
        type_heatmap_identity=type_heatmap_identity,
    )

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
    required_visual_families = int(getattr(app_config, "MAX_FAMILY_VISUAL_COUNT", 12))
    min_visual_support = int(getattr(app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 20))
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
        top_k_paper = int(getattr(app_config, "PAPER_HEATMAP_TOP_K", 35))
        top_k_dangerous = int(getattr(app_config, "PAPER_DANGEROUS_HEATMAP_TOP_K", 25))
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
    type_prevalence_view_frames: list[pd.DataFrame] = []
    family_profiles_view_frames: list[pd.DataFrame] = []
    group_entropy_view_frames: list[pd.DataFrame] = []
    family_jsd_view_frames: list[pd.DataFrame] = []
    discriminability_view_frames: list[pd.DataFrame] = []
    for view_name, matrix_df in permission_matrix_by_view.items():
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
        ]
    )
    for extra_path in [
        type_prevalence_csv,
        type_entropy_csv,
        family_profiles_csv,
        family_entropy_csv,
        banker_enrichment_csv,
        banker_top15_csv,
        discriminability_csv,
        generic_summary_csv,
        jsd_csv,
        consensus_corr_csv,
        dangerous_stats_csv,
        banker_clusters_csv,
        banker_cluster_profiles_csv,
        selected_visual_families_csv,
        jsd_pair_verification_csv,
    ]:
        if isinstance(extra_path, str) and extra_path:
            paths.append(extra_path)
    for maybe_png in [type_heatmap_png, family_heatmap_png, banker_bar_png, generic_scatter_png, jsd_png]:
        if isinstance(maybe_png, str):
            paths.append(maybe_png)
    if isinstance(temporal_trends_png, str):
        paths.append(temporal_trends_png)
    paths.extend(paper_variant_paths)
    paths.extend(canonical_heatmap_paths)
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
    du.print_info(f"[REPORT] Permission trends artifacts exported: {bundle_dir}")
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
    grouped = (
        sample_core_df.groupby(["family_id", "family_canonical", "type_slug"], dropna=False)["sample_id"]
        .nunique()
        .reset_index(name="sample_count")
    )
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


def _export_banker_trends_line_plot(
    trends_df: pd.DataFrame,
    run_id: str,
    bundle_dir: Path,
) -> str | None:
    """Export line plot for banker-sensitive permission prevalence over quarter."""
    if not isinstance(trends_df, pd.DataFrame) or trends_df.empty:
        return None
    plot_df = trends_df.copy()
    plot_df = plot_df[plot_df["banker_sample_count"] >= 1].copy()
    if plot_df.empty:
        return None
    try:
        plt = _import_pyplot()

        fig, ax = plt.subplots(figsize=(12, 5))
        x_vals = np.arange(len(plot_df))
        series_map = {
            "banker_bind_accessibility_service_prevalence": "BIND_ACCESSIBILITY_SERVICE",
            "banker_system_alert_window_prevalence": "SYSTEM_ALERT_WINDOW",
            "banker_request_install_packages_prevalence": "REQUEST_INSTALL_PACKAGES",
            "banker_read_sms_prevalence": "READ_SMS",
            "banker_receive_sms_prevalence": "RECEIVE_SMS",
            "banker_send_sms_prevalence": "SEND_SMS",
        }
        max_lines = max(int(getattr(app_config, "MAX_TIME_SERIES_LINES", 4)), 1)
        ranked_series = sorted(
            series_map.items(),
            key=lambda item: float(pd.to_numeric(plot_df[item[0]], errors="coerce").fillna(0.0).mean()),
            reverse=True,
        )
        for col, label in ranked_series[:max_lines]:
            y_vals = pd.to_numeric(plot_df[col], errors="coerce")
            ax.plot(x_vals, y_vals, marker="o", linewidth=1.8, label=label)
        ax.set_xticks(x_vals)
        ax.set_xticklabels(plot_df["period_quarter"].astype(str), rotation=45, ha="right")
        ax.set_ylim(0.0, 1.0)
        ax.set_ylabel("Prevalence in banker samples")
        ax.set_xlabel("Quarter")
        ax.set_title("Banker Sensitive Permission Trends Over Time")
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.legend(loc="upper left", ncol=2, fontsize=8, frameon=False)
        plt.tight_layout()
        figures_dir = _resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_FIGURES)
        run_path = figures_dir / f"banker_permission_trends_over_time_{run_id}.png"
        latest_path = figures_dir / "banker_permission_trends_over_time.latest.png"
        write_run_scoped = _write_run_scoped_permission_artifacts()
        fig.savefig(latest_path, dpi=_report_figure_dpi(), bbox_inches="tight")
        if write_run_scoped:
            fig.savefig(run_path, dpi=_report_figure_dpi(), bbox_inches="tight")
        plt.close(fig)
        return str(run_path if write_run_scoped else latest_path)
    except Exception as exc:
        _handle_reporting_exception("banker_trends_line_plot", exc, fail_in_paper=True)
        return None


def _extract_selected_vendors(feature_df: pd.DataFrame | None) -> list[str]:
    if not isinstance(feature_df, pd.DataFrame):
        return []
    selected = feature_df.attrs.get("selected_vendors", [])
    if not isinstance(selected, list):
        return []
    return [str(v).strip().lower() for v in selected if str(v).strip()]


def _build_consensus_distribution(
    sample_core_df: pd.DataFrame,
    parsed_data: dict[str, pd.DataFrame],
    selected_vendors: list[str],
    run_id: str,
) -> pd.DataFrame:
    base = sample_core_df[["sample_id", "sha256", "family_id", "family_canonical", "type_slug"]].copy()
    votes_df = _build_vendor_votes(parsed_data)
    if votes_df.empty:
        base["run_id"] = run_id
        base["vendor_count"] = 0
        base["top1_vote_share"] = 0.0
        base["top2_vote_share"] = 0.0
        base["top1_minus_top2_gap"] = 0.0
        base["consensus_score_all_vendors"] = 0.0
        base["consensus_entropy_all_vendors"] = 0.0
        base["consensus_score_gated_vendors"] = 0.0
        base["consensus_entropy_gated_vendors"] = 0.0
        base["low_vendor_count_flag"] = 1
        return base

    all_consensus = _compute_consensus_metrics(votes_df, prefix="all")
    if selected_vendors:
        gated_votes = votes_df[votes_df["vendor"].isin(set(selected_vendors))].copy()
    else:
        gated_votes = votes_df.copy()
    gated_consensus = _compute_consensus_metrics(gated_votes, prefix="gated")

    merged = base.merge(all_consensus, on="sample_id", how="left")
    merged = merged.merge(gated_consensus, on="sample_id", how="left")
    numeric_cols = [
        "vendor_count_all",
        "top1_vote_share_all",
        "top2_vote_share_all",
        "top1_minus_top2_gap_all",
        "consensus_score_all_vendors",
        "consensus_entropy_all_vendors",
        "vendor_count_gated",
        "consensus_score_gated_vendors",
        "consensus_entropy_gated_vendors",
    ]
    for col in numeric_cols:
        merged[col] = pd.to_numeric(merged.get(col, 0), errors="coerce").fillna(0.0)

    merged["run_id"] = run_id
    merged["vendor_count"] = merged["vendor_count_all"].astype(int)
    merged["top1_vote_share"] = merged["top1_vote_share_all"]
    merged["top2_vote_share"] = merged["top2_vote_share_all"]
    merged["top1_minus_top2_gap"] = merged["top1_minus_top2_gap_all"]
    min_vendor_count = int(getattr(app_config, "CONSENSUS_MIN_VENDOR_COUNT", 5))
    merged["low_vendor_count_flag"] = (merged["vendor_count"] < min_vendor_count).astype(int)
    keep_cols = [
        "run_id",
        "sample_id",
        "sha256",
        "family_id",
        "family_canonical",
        "type_slug",
        "vendor_count",
        "top1_vote_share",
        "top2_vote_share",
        "top1_minus_top2_gap",
        "consensus_score_all_vendors",
        "consensus_entropy_all_vendors",
        "consensus_score_gated_vendors",
        "consensus_entropy_gated_vendors",
        "low_vendor_count_flag",
    ]
    return merged[keep_cols].sort_values("sample_id").reset_index(drop=True)


def _build_vendor_votes(parsed_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for vendor, frame in parsed_data.items():
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        if "sample_id" not in frame.columns:
            continue
        parsed_col = _find_column(frame, "Parsed Family")
        if not parsed_col:
            continue
        subset = frame[["sample_id", parsed_col]].copy()
        subset["sample_id"] = pd.to_numeric(subset["sample_id"], errors="coerce")
        subset = subset.dropna(subset=["sample_id"])
        subset["sample_id"] = subset["sample_id"].astype(int)
        subset["parsed_family"] = subset[parsed_col].fillna("").astype(str).str.strip().str.lower()
        subset = subset[subset["parsed_family"] != ""]
        if subset.empty:
            continue
        subset["vendor"] = str(vendor).strip().lower()
        rows.extend(
            {
                "sample_id": int(sample_id),
                "vendor": str(vname),
                "parsed_family": str(pfamily),
            }
            for sample_id, vname, pfamily in subset[["sample_id", "vendor", "parsed_family"]].itertuples(index=False)
        )
    if not rows:
        return pd.DataFrame(columns=["sample_id", "vendor", "parsed_family"])
    out = pd.DataFrame(rows)
    out = out.drop_duplicates(subset=["sample_id", "vendor"])
    return out


def _find_column(frame: pd.DataFrame, expected: str) -> str | None:
    lowered = {str(col).strip().lower(): str(col) for col in frame.columns}
    return lowered.get(expected.strip().lower())


def _compute_consensus_metrics(votes_df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for sample_id, group in votes_df.groupby("sample_id", dropna=False):
        labels = group["parsed_family"].tolist()
        total = len(labels)
        if total <= 0:
            continue
        counts = Counter(labels)
        shares = sorted([count / total for count in counts.values()], reverse=True)
        top1 = float(shares[0]) if shares else 0.0
        top2 = float(shares[1]) if len(shares) > 1 else 0.0
        n_labels = len(counts)
        entropy = 0.0
        for share in shares:
            if share > 0:
                entropy += -(share * log(share))
        if n_labels > 1:
            entropy = float(entropy / log(n_labels))
        else:
            entropy = 0.0
        records.append(
            {
                "sample_id": int(sample_id),
                f"vendor_count_{prefix}": int(total),
                f"top1_vote_share_{prefix}": round(top1, 6),
                f"top2_vote_share_{prefix}": round(top2, 6),
                f"top1_minus_top2_gap_{prefix}": round(top1 - top2, 6),
                f"consensus_score_{'all_vendors' if prefix == 'all' else 'gated_vendors'}": round(top1, 6),
                f"consensus_entropy_{'all_vendors' if prefix == 'all' else 'gated_vendors'}": round(entropy, 6),
            }
        )
    return pd.DataFrame(records)


def _build_generic_definition_audit(
    sample_core_df: pd.DataFrame,
    family_support_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    min_support = int(getattr(app_config, "GENERIC_MIN_SUPPORT", 30))
    support_map = family_support_df.set_index("family_id")["sample_count"].to_dict()
    merged = sample_core_df[["sample_id", "family_id", "type_slug"]].merge(
        consensus_df[["sample_id", "consensus_score_all_vendors", "consensus_entropy_all_vendors", "vendor_count"]],
        on="sample_id",
        how="left",
    )
    merged["family_support"] = merged["family_id"].map(support_map).fillna(0).astype(int)
    merged["is_low_support_family"] = (merged["family_support"] < min_support).astype(int)
    merged["is_generic_primary"] = (
        (merged["type_slug"] == "unknown") | (merged["family_id"] < 0)
    ).astype(int)
    min_vendor_count = int(getattr(app_config, "CONSENSUS_MIN_VENDOR_COUNT", 5))
    valid = merged[merged["vendor_count"] >= min_vendor_count]
    if valid.empty:
        low_consensus_threshold = 0.0
    else:
        low_consensus_threshold = float(valid["consensus_score_all_vendors"].quantile(0.10))
    merged["is_generic_low_consensus"] = (
        merged["consensus_score_all_vendors"].fillna(0.0) <= low_consensus_threshold
    ).astype(int)
    merged["generic_low_support_overlap"] = (
        (merged["is_generic_primary"] == 1) & (merged["is_low_support_family"] == 1)
    ).astype(int)

    n = max(len(merged), 1)
    summary_rows = [
        {"run_id": run_id, "metric": "sample_count", "value": int(len(merged))},
        {
            "run_id": run_id,
            "metric": "generic_primary_count",
            "value": int(merged["is_generic_primary"].sum()),
        },
        {
            "run_id": run_id,
            "metric": "generic_primary_pct",
            "value": round(float(merged["is_generic_primary"].sum()) / n, 6),
        },
        {
            "run_id": run_id,
            "metric": "low_support_family_count",
            "value": int(merged["is_low_support_family"].sum()),
        },
        {
            "run_id": run_id,
            "metric": "low_support_family_pct",
            "value": round(float(merged["is_low_support_family"].sum()) / n, 6),
        },
        {
            "run_id": run_id,
            "metric": "generic_low_support_overlap_count",
            "value": int(merged["generic_low_support_overlap"].sum()),
        },
        {
            "run_id": run_id,
            "metric": "low_consensus_threshold_p10",
            "value": round(low_consensus_threshold, 6),
        },
        {
            "run_id": run_id,
            "metric": "generic_low_consensus_count",
            "value": int(merged["is_generic_low_consensus"].sum()),
        },
        {
            "run_id": run_id,
            "metric": "generic_low_consensus_pct",
            "value": round(float(merged["is_generic_low_consensus"].sum()) / n, 6),
        },
    ]
    return pd.DataFrame(summary_rows)


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


def _export_confusion_bar_plot(
    confusion_summary_df: pd.DataFrame,
    run_id: str,
    bundle_dir: Path,
) -> str | None:
    try:
        plt = _import_pyplot()
    except Exception:
        return None

    if confusion_summary_df.empty:
        return None
    subset = confusion_summary_df[
        confusion_summary_df["error_type"].isin(["within_type_error", "cross_type_error"])
    ].copy()
    if subset.empty:
        return None
    labels = subset["error_type"].tolist()
    values = pd.to_numeric(subset["count"], errors="coerce").fillna(0.0).tolist()
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(labels, values, color=["#1f77b4", "#ff7f0e"])
    ax.set_title("Within-type vs Cross-type Errors")
    ax.set_ylabel("Count")
    ax.set_xlabel("Error Type")
    fig.tight_layout()
    figures_dir = _resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_FIGURES)
    latest_path = figures_dir / "confusion_within_vs_cross_type.latest.png"
    fig.savefig(latest_path, dpi=_report_figure_dpi())
    run_path: Path | None = None
    if _write_run_scoped_permission_artifacts():
        run_path = figures_dir / f"confusion_within_vs_cross_type_{run_id}.png"
        fig.savefig(run_path, dpi=_report_figure_dpi())
    plt.close(fig)
    return str(run_path or latest_path)


def _export_prevalence_heatmap(
    prevalence_df: pd.DataFrame,
    row_field: str,
    value_field: str,
    run_id: str,
    file_stem: str,
    bundle_dir: Path,
    top_k: int = 30,
    selected_permissions: list[str] | None = None,
    title: str = "Permission prevalence heatmap",
) -> str | None:
    try:
        plt = _import_pyplot()
    except Exception:
        return None
    if prevalence_df.empty:
        return None
    if selected_permissions:
        allowed = {str(item).strip() for item in selected_permissions if str(item).strip()}
        support = [perm for perm in prevalence_df["permission"].astype(str).tolist() if perm in allowed]
    else:
        support = (
            prevalence_df.groupby("permission")["prevalence"]
            .mean()
            .sort_values(ascending=False)
            .head(top_k)
            .index
            .tolist()
        )
    subset = prevalence_df[prevalence_df["permission"].isin(support)].copy()
    if subset.empty:
        return None
    pivot = subset.pivot_table(index=row_field, columns="permission", values=value_field, fill_value=0.0)
    fig, ax = plt.subplots(figsize=(max(8, len(pivot.columns) * 0.35), max(4, len(pivot.index) * 0.45)))
    im = ax.imshow(pivot.values, aspect="auto", cmap="viridis", vmin=0, vmax=1)
    compact_labels = [_compact_permission_label(col) for col in pivot.columns]
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(compact_labels, rotation=90, fontsize=7)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=8)
    ax.set_title(title)
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    fig.tight_layout()
    figures_dir = _resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_FIGURES)
    latest_path = figures_dir / f"{file_stem}.latest.png"
    fig.savefig(latest_path, dpi=_report_figure_dpi())
    run_path: Path | None = None
    if _write_run_scoped_permission_artifacts():
        run_path = figures_dir / f"{file_stem}_{run_id}.png"
        fig.savefig(run_path, dpi=_report_figure_dpi())
    plt.close(fig)
    return str(run_path or latest_path)


def _export_jsd_heatmap(
    jsd_df: pd.DataFrame,
    run_id: str,
    file_stem: str,
    bundle_dir: Path,
) -> str | None:
    try:
        plt = _import_pyplot()
    except Exception:
        return None
    if jsd_df.empty:
        return None
    pivot = jsd_df.pivot_table(index=jsd_df.columns[1], columns="other", values="js_distance", fill_value=0.0)
    if pivot.empty:
        return None
    fig, ax = plt.subplots(figsize=(max(6, len(pivot.columns) * 0.45), max(5, len(pivot.index) * 0.45)))
    im = ax.imshow(pivot.values, aspect="auto", cmap="magma", vmin=0, vmax=1)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=90, fontsize=8)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=8)
    ax.set_title("Jensen-Shannon distance (top families)")
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    fig.tight_layout()
    figures_dir = _resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_FIGURES)
    latest_path = figures_dir / f"{file_stem}.latest.png"
    fig.savefig(latest_path, dpi=_report_figure_dpi())
    run_path: Path | None = None
    if _write_run_scoped_permission_artifacts():
        run_path = figures_dir / f"{file_stem}_{run_id}.png"
        fig.savefig(run_path, dpi=_report_figure_dpi())
    plt.close(fig)
    return str(run_path or latest_path)


def _export_banker_enrichment_bar_chart(
    banker_df: pd.DataFrame,
    run_id: str,
    bundle_dir: Path,
) -> str | None:
    try:
        plt = _import_pyplot()
    except Exception:
        return None
    if banker_df.empty:
        return None
    top = banker_df.sort_values("odds_ratio", ascending=False).head(15).copy()
    top = top.iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, max(5, len(top) * 0.35)))
    compact_labels = [_compact_permission_label(value) for value in top["permission"].tolist()]
    ax.barh(compact_labels, top["odds_ratio"], color="#2a9d8f")
    ax.set_xlabel("Odds Ratio (banker vs non-banker)")
    ax.set_ylabel("Permission")
    ax.set_title("Top 15 enriched permissions for banker")
    fig.tight_layout()
    figures_dir = _resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_FIGURES)
    latest_path = figures_dir / "banker_enrichment_top15.latest.png"
    fig.savefig(latest_path, dpi=_report_figure_dpi())
    run_path: Path | None = None
    if _write_run_scoped_permission_artifacts():
        run_path = figures_dir / f"banker_enrichment_top15_{run_id}.png"
        fig.savefig(run_path, dpi=_report_figure_dpi())
    plt.close(fig)
    return str(run_path or latest_path)


def _export_generic_scatter(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    run_id: str,
    bundle_dir: Path,
) -> str | None:
    try:
        plt = _import_pyplot()
    except Exception:
        return None
    metrics = _build_sample_level_permission_metrics(sample_core_df, permission_rows_df)
    min_vendor_count = int(getattr(app_config, "CONSENSUS_MIN_VENDOR_COUNT", 5))
    consensus_keep = consensus_df[consensus_df["vendor_count"] >= min_vendor_count][
        ["sample_id", "consensus_score_all_vendors"]
    ].copy()
    merged = sample_core_df[["sample_id", "type_slug", "family_id"]].merge(metrics, on="sample_id", how="left")
    merged = merged.merge(consensus_keep, on="sample_id", how="left")
    merged = merged.dropna(subset=["consensus_score_all_vendors"])
    if merged.empty:
        return None
    merged["is_generic"] = ((merged["type_slug"] == "unknown") | (merged["family_id"] < 0)).astype(int)
    fig, ax = plt.subplots(figsize=(7, 5))
    generic = merged[merged["is_generic"] == 1]
    non_generic = merged[merged["is_generic"] == 0]
    ax.scatter(non_generic["consensus_score_all_vendors"], non_generic["permission_entropy"], s=12, alpha=0.5, label="non-generic")
    ax.scatter(generic["consensus_score_all_vendors"], generic["permission_entropy"], s=12, alpha=0.6, label="generic")
    ax.set_xlabel("Consensus score (all vendors)")
    ax.set_ylabel("Permission entropy")
    ax.set_title("Consensus vs permission entropy")
    ax.legend(loc="best")
    fig.tight_layout()
    figures_dir = _resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_FIGURES)
    latest_path = figures_dir / "generic_consensus_vs_entropy.latest.png"
    fig.savefig(latest_path, dpi=_report_figure_dpi())
    run_path: Path | None = None
    if _write_run_scoped_permission_artifacts():
        run_path = figures_dir / f"generic_consensus_vs_entropy_{run_id}.png"
        fig.savefig(run_path, dpi=_report_figure_dpi())
    plt.close(fig)
    return str(run_path or latest_path)


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
    return pd.DataFrame(rows), pd.DataFrame(entropy_rows)


def _build_family_permission_profiles(
    sample_core_df: pd.DataFrame,
    permission_matrix_df: pd.DataFrame,
    run_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    supports = (
        sample_core_df.groupby(["family_id", "family_canonical"], dropna=False)["sample_id"]
        .nunique()
        .reset_index(name="sample_count")
        .sort_values("sample_count", ascending=False)
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
    keep = pd.concat([main.assign(profile_scope="main"), appendix.assign(profile_scope="appendix")], ignore_index=True)
    if keep.empty:
        return pd.DataFrame(), pd.DataFrame()
    merged = sample_core_df.merge(
        keep[["family_id", "family_canonical", "profile_scope"]],
        on=["family_id", "family_canonical"],
        how="inner",
    ).merge(permission_matrix_df, on="sample_id", how="left")
    permission_cols = [c for c in permission_matrix_df.columns if c != "sample_id"]
    if permission_cols:
        merged[permission_cols] = merged[permission_cols].fillna(0)
    rows: list[dict[str, Any]] = []
    entropy_rows: list[dict[str, Any]] = []
    for (family_id, family_name, scope), group in merged.groupby(
        ["family_id", "family_canonical", "profile_scope"], dropna=False
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
                    "profile_scope": str(scope),
                    "permission": permission,
                    "prevalence": round(prev, 6),
                    "sample_count": int(len(group)),
                }
            )
        entropy, eff_div = _prevalence_entropy(prevalences)
        entropy_rows.append(
            {
                "run_id": run_id,
                "family_id": int(family_id),
                "family_canonical": str(family_name),
                "profile_scope": str(scope),
                "sample_count": int(len(group)),
                "permission_entropy": round(entropy, 6),
                "effective_diversity": round(eff_div, 6),
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(entropy_rows)










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
    merged = sample_core_df[["sample_id", "type_slug"]].merge(permission_matrix_df, on="sample_id", how="left").fillna(0)
    permission_cols = [c for c in merged.columns if c not in {"sample_id", "type_slug"}]
    if not permission_cols:
        return pd.DataFrame()
    label = merged["type_slug"].astype(str)
    rows: list[dict[str, Any]] = []
    for permission in permission_cols:
        present = pd.to_numeric(merged[permission], errors="coerce").fillna(0).astype(int)
        p_value, cramers_v = _chi2_presence_vs_multiclass(label, present)
        rows.append(
            {
                "run_id": run_id,
                "permission": permission,
                "chi2_p_value": p_value,
                "cramers_v": cramers_v,
                "global_support": int(present.sum()),
            }
        )
    out = pd.DataFrame(rows)
    out["chi2_p_value_fdr_bh"] = _bh_fdr(out["chi2_p_value"].tolist())
    out["mutual_information"] = _mutual_information_scores(label, merged[permission_cols])
    return out.sort_values(["cramers_v", "mutual_information"], ascending=[False, False]).reset_index(drop=True)


def _chi2_presence_vs_multiclass(label: pd.Series, present: pd.Series) -> tuple[float, float]:
    table = pd.crosstab(label, present)
    if table.empty or table.shape[0] < 2 or table.shape[1] < 2:
        return 1.0, 0.0
    try:
        from scipy.stats import chi2_contingency

        chi2, p_value, _, _ = chi2_contingency(table.values, correction=False)
    except Exception:
        return 1.0, 0.0
    n = float(table.values.sum())
    k = min(table.shape[0] - 1, table.shape[1] - 1)
    if n <= 0 or k <= 0:
        return float(p_value), 0.0
    cramers_v = float(np.sqrt(max(chi2, 0.0) / (n * k)))
    return float(p_value), cramers_v


def _mutual_information_scores(label: pd.Series, features_df: pd.DataFrame) -> list[float]:
    try:
        from sklearn.feature_selection import mutual_info_classif
        from sklearn.preprocessing import LabelEncoder

        encoder = LabelEncoder()
        y = encoder.fit_transform(label.astype(str))
        x = features_df.astype(int).values
        scores = mutual_info_classif(x, y, discrete_features=True, random_state=42)
        return [round(float(s), 6) for s in scores]
    except Exception:
        return [0.0 for _ in range(features_df.shape[1])]


def _build_generic_vs_non_generic_summary(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
    permission_matrix_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    metrics_df = _build_sample_level_permission_metrics(sample_core_df, permission_rows_df)
    min_vendor_count = int(getattr(app_config, "CONSENSUS_MIN_VENDOR_COUNT", 5))
    consensus_keep = consensus_df[consensus_df["vendor_count"] >= min_vendor_count][
        ["sample_id", "consensus_score_all_vendors"]
    ].copy()
    merged = sample_core_df[["sample_id", "type_slug", "family_id"]].merge(metrics_df, on="sample_id", how="left")
    merged = merged.merge(consensus_keep, on="sample_id", how="left")
    merged["is_generic"] = ((merged["type_slug"] == "unknown") | (merged["family_id"] < 0)).astype(int)
    merged["permission_entropy"] = pd.to_numeric(merged.get("permission_entropy", 0.0), errors="coerce").fillna(0.0)
    merged["dangerous_count_strict"] = pd.to_numeric(merged.get("dangerous_count_strict", 0.0), errors="coerce").fillna(0.0)
    merged["dangerous_count_inclusive"] = pd.to_numeric(merged.get("dangerous_count_inclusive", 0.0), errors="coerce").fillna(0.0)
    merged["consensus_score_all_vendors"] = pd.to_numeric(
        merged.get("consensus_score_all_vendors", np.nan), errors="coerce"
    )

    rows: list[dict[str, Any]] = []
    for generic_flag, group in merged.groupby("is_generic", dropna=False):
        tag = "generic" if int(generic_flag) == 1 else "non_generic"
        rows.append(
            {
                "run_id": run_id,
                "group": tag,
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
    generic_values = merged[merged["is_generic"] == 1]
    non_generic_values = merged[merged["is_generic"] == 0]
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
    if permission_rows_df.empty:
        return sample_core_df[["sample_id"]].assign(
            permission_entropy=0.0,
            dangerous_count_strict=0,
            dangerous_count_inclusive=0,
        )
    work = permission_rows_df.copy()
    work["bucket"] = np.where(
        work["protection_level"].str.contains("DANGEROUS", regex=False),
        "dangerous",
        np.where(work["protection_level"].str.contains("NORMAL", regex=False), "normal", "unknown"),
    )
    counts = (
        work.groupby(["sample_id", "bucket"])["permission_string"]
        .count()
        .reset_index(name="count")
    )
    entropy_rows: list[dict[str, Any]] = []
    for sample_id, group in counts.groupby("sample_id"):
        vals = group["count"].astype(float).values
        probs = vals / vals.sum() if vals.sum() > 0 else np.array([1.0])
        entropy = float(-(probs * np.log(probs)).sum())
        strict = int(group[group["bucket"] == "dangerous"]["count"].sum())
        unknown = int(group[group["bucket"] == "unknown"]["count"].sum())
        entropy_rows.append(
            {
                "sample_id": int(sample_id),
                "permission_entropy": entropy,
                "dangerous_count_strict": strict,
                "dangerous_count_inclusive": strict + unknown,
            }
        )
    out = pd.DataFrame(entropy_rows)
    return sample_core_df[["sample_id"]].merge(out, on="sample_id", how="left").fillna(0)








def _build_consensus_correlation_report(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    run_id: str,
) -> tuple[pd.DataFrame, str]:
    metrics_df = _build_sample_level_permission_metrics(sample_core_df, permission_rows_df)
    min_vendor_count = int(getattr(app_config, "CONSENSUS_MIN_VENDOR_COUNT", 5))
    consensus_keep = consensus_df[consensus_df["vendor_count"] >= min_vendor_count][
        ["sample_id", "consensus_score_all_vendors"]
    ].copy()
    merged = metrics_df.merge(consensus_keep, on="sample_id", how="inner")
    if merged.empty:
        out = pd.DataFrame(
            [
                {
                    "run_id": run_id,
                    "metric_x": "consensus_score_all_vendors",
                    "metric_y": "permission_entropy",
                    "spearman_rho": 0.0,
                    "p_value": np.nan,
                    "ci_low": np.nan,
                    "ci_high": np.nan,
                    "n_samples": 0,
                }
            ]
        )
        text = "No valid samples after consensus vendor-count filtering; association analysis not computed.\n"
        return out, text

    rows: list[dict[str, Any]] = []
    checks = [
        ("permission_entropy", "consensus vs permission entropy"),
        ("dangerous_count_strict", "consensus vs dangerous_count_strict"),
        ("dangerous_count_inclusive", "consensus vs dangerous_count_inclusive"),
    ]
    lines = [f"Run ID: {run_id}", "Association analysis only (not causation).", ""]
    for metric, label in checks:
        x = pd.to_numeric(merged["consensus_score_all_vendors"], errors="coerce")
        y = pd.to_numeric(merged[metric], errors="coerce")
        rho, p_value, ci_low, ci_high = _spearman_with_bootstrap_ci(x, y)
        n = int(pd.concat([x, y], axis=1).dropna().shape[0])
        rows.append(
            {
                "run_id": run_id,
                "metric_x": "consensus_score_all_vendors",
                "metric_y": metric,
                "spearman_rho": round(rho, 6),
                "p_value": p_value,
                "ci_low": round(ci_low, 6),
                "ci_high": round(ci_high, 6),
                "n_samples": n,
            }
        )
        lines.append(
            f"- {label}: rho={rho:.4f}, 95% bootstrap CI=[{ci_low:.4f}, {ci_high:.4f}], p={p_value:.3e}, n={n}"
        )
    return pd.DataFrame(rows), "\n".join(lines) + "\n"






def _build_dangerous_stats_tests(
    sample_core_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    metrics_df = _build_sample_level_permission_metrics(sample_core_df, permission_rows_df)
    frame = sample_core_df[["sample_id", "type_slug"]].merge(metrics_df, on="sample_id", how="left").fillna(0)
    metric = "dangerous_count_strict"
    groups = {
        str(type_slug): pd.to_numeric(group[metric], errors="coerce").dropna().astype(float)
        for type_slug, group in frame.groupby("type_slug", dropna=False)
    }
    group_values = [vals.values for vals in groups.values() if len(vals) > 0]
    kw_stat = np.nan
    kw_p = np.nan
    if len(group_values) >= 2:
        try:
            from scipy.stats import kruskal

            kw = kruskal(*group_values)
            kw_stat = float(kw.statistic)
            kw_p = float(kw.pvalue)
        except Exception:
            pass
    rows: list[dict[str, Any]] = [
        {
            "run_id": run_id,
            "test_type": "kruskal_wallis",
            "metric": metric,
            "group_a": "all",
            "group_b": "all",
            "statistic": kw_stat,
            "p_value": kw_p,
            "p_value_fdr_bh": kw_p,
            "effect_size": np.nan,
            "effect_size_name": "epsilon_squared",
            "method_notes": "global_nonparametric",
        }
    ]
    pair_rows = _build_pairwise_dunn_or_mannwhitney(frame=frame, metric=metric, run_id=run_id, groups=groups)
    if pair_rows:
        rows.extend(pair_rows)
    return pd.DataFrame(rows)


def _build_pairwise_dunn_or_mannwhitney(
    frame: pd.DataFrame,
    metric: str,
    run_id: str,
    groups: dict[str, pd.Series],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # Preferred path for paper contract.
    try:
        import scikit_posthocs as sp

        dunn_matrix = sp.posthoc_dunn(
            frame[[metric, "type_slug"]].rename(columns={metric: "value", "type_slug": "group"}),
            val_col="value",
            group_col="group",
            p_adjust="fdr_bh",
        )
        keys = sorted(groups.keys())
        for i, left in enumerate(keys):
            for right in keys[i + 1 :]:
                p_value = float(dunn_matrix.loc[left, right]) if left in dunn_matrix.index and right in dunn_matrix.columns else np.nan
                rows.append(
                    {
                        "run_id": run_id,
                        "test_type": "pairwise_dunn",
                        "metric": metric,
                        "group_a": left,
                        "group_b": right,
                        "statistic": np.nan,
                        "p_value": p_value,
                        "p_value_fdr_bh": p_value,
                        "effect_size": round(_cliffs_delta(groups[left], groups[right]), 6),
                        "effect_size_name": "cliffs_delta",
                        "method_notes": "dunn_with_bh_fdr",
                    }
                )
        return rows
    except Exception:
        pass

    # Fallback path when scikit-posthocs is unavailable.
    keys = sorted(groups.keys())
    for i, left in enumerate(keys):
        for right in keys[i + 1 :]:
            a = groups[left]
            b = groups[right]
            if a.empty or b.empty:
                continue
            p_value = np.nan
            stat = np.nan
            try:
                from scipy.stats import mannwhitneyu

                res = mannwhitneyu(a.values, b.values, alternative="two-sided")
                stat = float(res.statistic)
                p_value = float(res.pvalue)
            except Exception:
                pass
            rows.append(
                {
                    "run_id": run_id,
                    "test_type": "pairwise_mannwhitney",
                    "metric": metric,
                    "group_a": left,
                    "group_b": right,
                    "statistic": stat,
                    "p_value": p_value,
                    "effect_size": round(_cliffs_delta(a, b), 6),
                    "effect_size_name": "cliffs_delta",
                    "method_notes": "pairwise_nonparametric_fallback_for_dunn",
                }
            )
    if not rows:
        return rows
    pair_df = pd.DataFrame(rows)
    pair_df["p_value_fdr_bh"] = _bh_fdr(pair_df["p_value"].fillna(1.0).astype(float).tolist())
    return pair_df.to_dict(orient="records")


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
    requested_k = int(getattr(app_config, "BANKER_PATTERN_CLUSTER_K", 3))
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
    min_selected = int(getattr(app_config, "FEATURE_MIN_SELECTED_VENDORS", 1))
    vendor_constrained = len(selected_vendors) < min_selected
    snapshot_meta = {
        "selection_rule_version": str(
            getattr(app_config, "ANALYSIS_SELECTION_RULE_VERSION", "snapshot_v1")
        ),
        "min_support": int(getattr(app_config, "GENERIC_MIN_SUPPORT", 30)),
        "permission_global_support_floor_rule": "max(50,1%)",
    }
    snapshot_meta.update(_read_snapshot_meta())
    excluded_low_vendor = int(
        pd.to_numeric(consensus_df.get("low_vendor_count_flag", 0), errors="coerce").fillna(0).sum()
    ) if isinstance(consensus_df, pd.DataFrame) and not consensus_df.empty else 0
    temporal_summary = _build_temporal_summary(sample_core_df)
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
        "feature_top_k": int(getattr(app_config, "FEATURE_TOP_K", 8)),
        "consensus_formula_version": "v1_top_vote_share_normalized_entropy",
        "consensus_min_vendor_count": int(getattr(app_config, "CONSENSUS_MIN_VENDOR_COUNT", 5)),
        "consensus_bootstrap_resamples": int(getattr(app_config, "CONSENSUS_BOOTSTRAP_RESAMPLES", 2000)),
        "banker_pattern_cluster_k": int(getattr(app_config, "BANKER_PATTERN_CLUSTER_K", 3)),
        "permission_support_floor": int(permission_support_floor),
        "kept_permission_count": int(kept_permission_count),
        "permission_pattern_policy": {
            "primary_view": PRIMARY_PERMISSION_VIEW,
            "views": ["inclusive", "aosp_only", "ecosystem"],
            "permission_alias_map_version": PERMISSION_ALIAS_MAP_VERSION,
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


def _export_selected_visual_family_registry(
    *,
    sample_core_df: pd.DataFrame,
    visual_families: list[str],
    run_id: str,
) -> str:
    """Export deterministic visual-family selection registry for paper traceability."""
    diagnostics_dir = Path(
        str(
            getattr(
                app_config,
                "RUNTIME_DIAGNOSTICS_DIR",
                Path(app_config.DEFAULT_OUTPUT_DIR) / "diagnostics",
            )
        )
    )
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    min_support = int(getattr(app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 20))
    max_count = int(getattr(app_config, "MAX_FAMILY_VISUAL_COUNT", 12))
    selected_set = {str(name) for name in visual_families}

    registry_df = pd.DataFrame(
        columns=[
            "rank",
            "family_canonical",
            "type_slug",
            "sample_count",
            "selected_reason",
        ]
    )
    if isinstance(sample_core_df, pd.DataFrame) and not sample_core_df.empty and selected_set:
        work = sample_core_df.copy()
        work["family_canonical"] = work.get("family_canonical", "").astype(str).str.strip()
        work["type_slug"] = work.get("type_slug", "").astype(str).str.strip().str.lower()
        work = work[work["family_canonical"].isin(selected_set)].copy()
        if not work.empty:
            summary = (
                work.groupby(["family_canonical", "type_slug"], as_index=False)
                .size()
                .rename(columns={"size": "sample_count"})
                .sort_values(
                    by=["sample_count", "family_canonical", "type_slug"],
                    ascending=[False, True, True],
                    kind="mergesort",
                )
            )
            dedup = summary.drop_duplicates(subset=["family_canonical"], keep="first").copy()
            dedup = dedup.sort_values(
                by=["sample_count", "family_canonical"],
                ascending=[False, True],
                kind="mergesort",
            ).reset_index(drop=True)
            dedup["rank"] = dedup.index + 1
            dedup["selected_reason"] = (
                f"support>={max(min_support, 1)};top_{max(max_count, 1)}_by_sample_count"
            )
            registry_df = dedup[
                ["rank", "family_canonical", "type_slug", "sample_count", "selected_reason"]
            ].copy()

    run_path = diagnostics_dir / f"selected_families_visual_{run_id}.csv"
    latest_path = diagnostics_dir / "selected_families_visual.latest.csv"
    registry_df.to_csv(run_path, index=False)
    registry_df.to_csv(latest_path, index=False)
    setattr(app_config, "RUNTIME_SELECTED_FAMILIES_VISUAL_PATH", str(run_path))
    return str(run_path)


def _export_jsd_support_shortfall_artifact(
    *,
    run_id: str,
    selected_count: int,
    required_count: int,
    min_support: int,
) -> str:
    """Export explicit JSD shortfall diagnostics when policy cannot be met."""
    diagnostics_dir = Path(
        str(
            getattr(
                app_config,
                "RUNTIME_DIAGNOSTICS_DIR",
                Path(app_config.DEFAULT_OUTPUT_DIR) / "diagnostics",
            )
        )
    )
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    payload = pd.DataFrame(
        [
            {
                "run_id": str(run_id),
                "jsd_family_support_shortfall": 1,
                "selected_family_count": int(selected_count),
                "required_family_count": int(required_count),
                "min_support": int(min_support),
            }
        ]
    )
    run_path = diagnostics_dir / f"jsd_family_support_shortfall_{run_id}.csv"
    latest_path = diagnostics_dir / "jsd_family_support_shortfall.latest.csv"
    payload.to_csv(run_path, index=False)
    payload.to_csv(latest_path, index=False)
    return str(run_path)


def _export_jsd_pair_verification(
    *,
    jsd_df: pd.DataFrame,
    run_id: str,
    bundle_dir: Path | None = None,
    file_stem: str = "family_jsd_pairs_top12",
) -> str | None:
    """Export compact unordered JSD family-pair table (no diagonal, no mirrored duplicates)."""
    if not isinstance(jsd_df, pd.DataFrame) or jsd_df.empty:
        return None
    family_col = str(jsd_df.columns[1]) if len(jsd_df.columns) > 1 else ""
    if not family_col or "other" not in jsd_df.columns or "js_distance" not in jsd_df.columns:
        return None
    work = jsd_df[[family_col, "other", "js_distance"]].copy()
    left = work[family_col].astype(str).str.strip()
    right = work["other"].astype(str).str.strip()
    work = work[left != right].copy()
    if work.empty:
        return None
    work["family_a"] = np.where(
        work[family_col].astype(str) <= work["other"].astype(str),
        work[family_col].astype(str),
        work["other"].astype(str),
    )
    work["family_b"] = np.where(
        work[family_col].astype(str) <= work["other"].astype(str),
        work["other"].astype(str),
        work[family_col].astype(str),
    )
    compact = (
        work.groupby(["family_a", "family_b"], as_index=False)["js_distance"]
        .mean()
        .sort_values(by=["family_a", "family_b"], ascending=[True, True], kind="mergesort")
    )
    compact.insert(0, "run_id", str(run_id))
    diagnostics_dir = Path(
        str(
            getattr(
                app_config,
                "RUNTIME_DIAGNOSTICS_DIR",
                Path(app_config.DEFAULT_OUTPUT_DIR) / "diagnostics",
            )
        )
    )
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_path = diagnostics_dir / f"family_jsd_pairs_verification_{run_id}.csv"
    latest_path = diagnostics_dir / "family_jsd_pairs_verification.latest.csv"
    compact.to_csv(run_path, index=False)
    compact.to_csv(latest_path, index=False)
    bundle_path: str | None = None
    if isinstance(bundle_dir, Path):
        bundle_path = _export_df_with_latest(
            compact,
            run_id=run_id,
            file_stem=file_stem,
            bundle_dir=bundle_dir,
        )
    setattr(app_config, "RUNTIME_FAMILY_JSD_PAIR_VERIFICATION_PATH", str(run_path))
    return str(bundle_path) if isinstance(bundle_path, str) and bundle_path else str(run_path)


def _export_family_permission_heatmap(
    family_profiles_df: pd.DataFrame,
    visual_families: list[str],
    run_id: str,
    bundle_dir: Path,
    file_stem: str = "family_permission_heatmap_top12",
) -> str | None:
    """Export pruned family-permission prevalence heatmap for paper readability."""
    if not isinstance(family_profiles_df, pd.DataFrame) or family_profiles_df.empty or not visual_families:
        return None
    max_perms = int(getattr(app_config, "MAX_FAMILY_HEATMAP_PERMISSIONS", 25))
    scope_df = family_profiles_df.copy()
    if "profile_scope" in scope_df.columns:
        scope_df = scope_df[scope_df["profile_scope"].astype(str) == "main"].copy()
    scope_df = scope_df[scope_df["family_canonical"].astype(str).isin(set(visual_families))].copy()
    if scope_df.empty:
        return None
    return _export_prevalence_heatmap(
        prevalence_df=scope_df,
        row_field="family_canonical",
        value_field="prevalence",
        run_id=run_id,
        file_stem=file_stem,
        bundle_dir=bundle_dir,
        top_k=max(max_perms, 1),
        title=f"Family permission heatmap (top {max(max_perms, 1)})",
    )


def _build_permission_trends_layout_check(bundle_dir: Path) -> dict[str, Any]:
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


def _export_alias_map_csv(run_id: str, bundle_dir: Path) -> str:
    df = pd.DataFrame(
        [{"alias_from": key, "alias_to": value} for key, value in sorted(PERMISSION_ALIAS_MAP.items())]
    )
    contracts_dir = _resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_CONTRACTS)
    latest_path = contracts_dir / "permission_alias_map.latest.csv"
    run_path: Path | None = None
    if _write_run_scoped_permission_artifacts():
        run_path = contracts_dir / f"permission_alias_map_{run_id}.csv"
        df.to_csv(run_path, index=False)
    df.to_csv(latest_path, index=False)
    return str(run_path or latest_path)


def _export_safe_claims_report(
    run_id: str,
    bundle_dir: Path,
    coverage_df: pd.DataFrame,
    banker_enrichment_df: pd.DataFrame,
    dangerous_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    selected_vendor_count: int,
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
        top = _select_banker_summary_rows(banker_enrichment_df, limit=3)
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
    if selected_vendor_count < int(getattr(app_config, "FEATURE_MIN_SELECTED_VENDORS", 1)):
        lines.append("- This run is vendor-constrained; avoid broad ablation generalization.")
    lines.append("- Do not infer runtime behavior from static manifest permissions.")
    lines.append("- Do not over-interpret family-level inferential stats below support threshold.")

    docs_dir = _resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_DOCS)
    latest_path = docs_dir / "safe_claims.latest.txt"
    text = "\n".join(lines) + "\n"
    run_path: Path | None = None
    if _write_run_scoped_permission_artifacts():
        run_path = docs_dir / f"safe_claims_{run_id}.txt"
        run_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return str(run_path or latest_path)


def _export_paper_figures_index(
    run_id: str,
    bundle_dir: Path,
    type_heatmap_png: str | None,
    banker_bar_png: str | None,
    generic_scatter_png: str | None,
    jsd_png: str | None,
    temporal_trends_png: str | None,
    banker_enrichment_csv: str,
) -> str:
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
    docs_dir = _resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_DOCS)
    latest_path = docs_dir / "paper_figures_index.latest.md"
    text = "\n".join(lines) + "\n"
    run_path: Path | None = None
    if _write_run_scoped_permission_artifacts():
        run_path = docs_dir / f"paper_figures_index_{run_id}.md"
        run_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return str(run_path or latest_path)


def _export_run_summary_onepager(
    run_id: str,
    profile_id: str,
    bundle_dir: Path,
    coverage_df: pd.DataFrame,
    dangerous_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    bundle_metadata: dict[str, Any],
    banker_enrichment_df: pd.DataFrame,
) -> str:
    coverage = coverage_df.iloc[0].to_dict() if not coverage_df.empty else {}
    unknown_rate = float(dangerous_df["unknown_protection_rate"].mean()) if not dangerous_df.empty else 0.0
    excluded = int(pd.to_numeric(consensus_df.get("low_vendor_count_flag", 0), errors="coerce").fillna(0).sum()) if isinstance(consensus_df, pd.DataFrame) and not consensus_df.empty else 0
    top = _select_banker_summary_rows(banker_enrichment_df, limit=5) if not banker_enrichment_df.empty else pd.DataFrame()
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
    lines.extend([
        "",
        "Top banker enrichment (AOSP-only primary):",
    ])
    if top.empty:
        lines.append("- No banker enrichment rows available.")
    else:
        for _, row in top.iterrows():
            lines.append(
                f"- {row['permission']}: OR={float(row['odds_ratio']):.3f}, FDR={float(row['p_value_fdr_bh']):.3e}"
            )
    docs_dir = _resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_DOCS)
    latest_path = docs_dir / "run_summary_onepager.latest.md"
    text = "\n".join(lines) + "\n"
    run_path: Path | None = None
    if _write_run_scoped_permission_artifacts():
        run_path = docs_dir / f"run_summary_onepager_{run_id}.md"
        run_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return str(run_path or latest_path)


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


def _export_df_with_latest(
    df: pd.DataFrame,
    run_id: str,
    file_stem: str,
    bundle_dir: Path,
) -> str:
    tables_dir = _resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_TABLES)
    latest_path = tables_dir / f"{file_stem}.latest.csv"
    run_path: Path | None = None
    if _write_run_scoped_permission_artifacts():
        run_path = tables_dir / f"{file_stem}_{run_id}.csv"
        df.to_csv(run_path, index=False)
    df.to_csv(latest_path, index=False)
    return str(run_path or latest_path)


def _export_df_diagnostics_with_latest(
    df: pd.DataFrame,
    *,
    run_id: str,
    file_stem: str,
) -> str:
    """Export CSV to run diagnostics with run-scoped + latest variants."""
    diagnostics_dir = Path(
        str(
            getattr(
                app_config,
                "RUNTIME_DIAGNOSTICS_DIR",
                Path(app_config.DEFAULT_OUTPUT_DIR) / "diagnostics",
            )
        )
    )
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_path = diagnostics_dir / f"{file_stem}_{run_id}.csv"
    latest_path = diagnostics_dir / f"{file_stem}.latest.csv"
    df.to_csv(run_path, index=False)
    df.to_csv(latest_path, index=False)
    return str(run_path)


def _export_json_with_latest(
    payload: dict[str, Any],
    run_id: str,
    file_stem: str,
    bundle_dir: Path,
) -> str:
    contracts_dir = _resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_CONTRACTS)
    latest_path = contracts_dir / f"{file_stem}.latest.json"
    run_path: Path | None = None
    if _write_run_scoped_permission_artifacts():
        run_path = contracts_dir / f"{file_stem}_{run_id}.json"
        run_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    latest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(run_path or latest_path)


def _export_text_with_latest(
    text: str,
    run_id: str,
    file_stem: str,
    bundle_dir: Path,
) -> str:
    docs_dir = _resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_DOCS)
    latest_path = docs_dir / f"{file_stem}.latest.txt"
    run_path: Path | None = None
    if _write_run_scoped_permission_artifacts():
        run_path = docs_dir / f"{file_stem}_{run_id}.txt"
        run_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return str(run_path or latest_path)


def _export_permission_trends_bundle_readme(run_id: str, bundle_dir: Path) -> str:
    """Write operator-readable scope notes for the permission_trends bundle."""
    lines = [
        "# Permission Trends Bundle",
        "",
        f"- run_id: {run_id}",
        f"- bundle_contract_name: {BUNDLE_CONTRACT_NAME}",
        f"- bundle_contract_version: {BUNDLE_CONTRACT_VERSION}",
        "",
        "This bundle contains full structural-analysis research artifacts.",
        "",
        "Directory semantics:",
        "- contracts/: bundle contracts and machine-readable metadata.",
        "- docs/: operator-readable notes and narrative summaries.",
        "- figures/: structural analysis figures.",
        "- tables/: structural analysis tables.",
        "",
        "Related run directories:",
        "- diagnostics/: QA, provenance, and validation outputs.",
        "- paper_exports/: strict paper subset (paper mode only).",
        "- models/: trained model artifacts.",
        "- conf_matrices/: model confusion matrices.",
    ]
    readme_path = bundle_dir / "README.md"
    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(readme_path)


def _zip_bundle(bundle_dir: Path) -> str:
    zip_path = bundle_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in bundle_dir.rglob("*"):
            if path.is_file():
                archive.write(path, arcname=str(path.relative_to(bundle_dir.parent)))
    return str(zip_path)


def _resolve_permission_bundle_dir(run_id: str) -> Path:
    """Resolve output folder for permission trends bundle."""
    run_id_clean = str(run_id).strip()
    if run_id_clean:
        return _resolve_run_root_for_run_id(run_id_clean) / "bundles" / "permission_trends"
    return output_paths.output_root() / "tools" / "permission_trends"


def _copy_permission_bundle_to_latest(bundle_dir: Path) -> Path | None:
    """Best-effort copy of canonical bundle into mutable latest location."""
    if not bool(getattr(app_config, "ENABLE_PERMISSION_TRENDS_LATEST_MIRROR", False)):
        return None
    if not isinstance(bundle_dir, Path) or not bundle_dir.exists():
        return None
    latest_dir = output_paths.bundles_root() / "latest" / "permission_trends"
    try:
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(bundle_dir, latest_dir)
        return latest_dir
    except Exception as exc:
        du.print_warning(f"[REPORT] Latest permission bundle copy skipped (non-fatal): {exc}")
        return None
