"""Strict Paper #2 export bundle (figures, tables, registries, validation).

Canonical implementation under ``obsidiandroid.pipeline.manifest.paper2_strict_exports``;
extracted from ``obsidiandroid.pipeline.stage_manifest`` to reduce stage file size.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from config import app_config

from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.pipeline.manifest.confusion_matrix_paths import find_primary_confusion_matrix
from obsidiandroid.pipeline.manifest.hashing import sha256_hex
from obsidiandroid.pipeline.manifest.paper_figure_renderers import (
    annotate_confusion_matrix_with_metrics,
    export_paper_figure_qc,
    render_paper_dangerous_distribution_from_table,
    render_paper_jsd_heatmap_from_pairs,
    render_paper_type_heatmap_from_table,
    render_pipeline_architecture_figure,
)
from obsidiandroid.reporting.latex_tables import LatexTableSpec, render_tabular

def build_paper_model_comparison_table(*, source_path: Path, output_path: Path) -> None:
    """Build compact paper model-comparison table for RF/XGB/LR only."""
    src_df = pd.read_csv(source_path)
    if src_df.empty:
        pd.DataFrame(columns=["model", "macro_f1", "accuracy"]).to_csv(output_path, index=False)
        return
    model_col = "Model" if "Model" in src_df.columns else ("model" if "model" in src_df.columns else "")
    macro_col = (
        "MacroF1"
        if "MacroF1" in src_df.columns
        else (
            "Macro F1-Score"
            if "Macro F1-Score" in src_df.columns
            else ("macro_f1" if "macro_f1" in src_df.columns else "")
        )
    )
    acc_col = (
        "Acc"
        if "Acc" in src_df.columns
        else ("Accuracy" if "Accuracy" in src_df.columns else ("accuracy" if "accuracy" in src_df.columns else ""))
    )
    if not model_col or not macro_col or not acc_col:
        src_df.to_csv(output_path, index=False)
        return
    keep_map = {
        "rf": "random_forest",
        "random_forest": "random_forest",
        "xgb": "xgboost",
        "xgboost": "xgboost",
        "log_reg": "logistic_regression",
        "logistic_regression": "logistic_regression",
    }
    work = src_df[[model_col, macro_col, acc_col]].copy()
    work["model"] = work[model_col].astype(str).str.strip().str.lower().map(keep_map)
    work = work[work["model"].isin({"random_forest", "xgboost", "logistic_regression"})].copy()
    work["macro_f1"] = pd.to_numeric(work[macro_col], errors="coerce")
    work["accuracy"] = pd.to_numeric(work[acc_col], errors="coerce")
    order = {"random_forest": 0, "xgboost": 1, "logistic_regression": 2}
    work["order"] = work["model"].map(order).fillna(99).astype(int)
    out = (
        work.sort_values(by=["order", "model"], ascending=[True, True], kind="mergesort")
        .drop_duplicates(subset=["model"], keep="first")
        [["model", "macro_f1", "accuracy"]]
    )
    out.to_csv(output_path, index=False, float_format="%.6f")



def write_table_latex_from_csv(*, csv_path: Path, tex_path: Path) -> None:
    """Render a compact LaTeX tabular from a CSV table."""
    df = pd.read_csv(csv_path)
    ncols = len(df.columns)
    align = "l" + "r" * max(ncols - 1, 0)
    tex_path.write_text(
        render_tabular(df, spec=LatexTableSpec(align=align, use_booktabs=False)),
        encoding="utf-8",
    )



def build_paper_registry_payload(
    *,
    run_root: Path,
    run_id: str,
    contract_version: str,
    figure_registry_rows: list[dict[str, Any]],
    table_registry_rows: list[dict[str, Any]],
    latex_paths: dict[str, str],
    blocked_non_paper_ids: set[str],
) -> dict[str, Any]:
    """Build unified paper artifact registry for deterministic manuscript mapping."""
    artifacts_out: list[dict[str, Any]] = []
    for row in figure_registry_rows:
        artifact_id = str(row.get("figure_id", "")).strip()
        temp_destination_path = str(row.get("destination_path", "")).strip()
        destination_filename = str(row.get("destination_filename", "")).strip()
        destination_path = (
            str((run_root / "paper_exports" / "figures" / destination_filename).resolve())
            if destination_filename
            else ""
        )
        source_path = str(row.get("source_path", "")).strip()
        sha = (
            sha256_hex(Path(temp_destination_path).read_bytes())
            if temp_destination_path and Path(temp_destination_path).exists()
            else ""
        )
        artifacts_out.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": "figure",
                "run_id": str(run_id),
                "source_path": source_path,
                "destination_path": destination_path,
                "sha256": sha,
                "paper_allowed": True,
                "contract_version": str(contract_version),
            }
        )
    for row in table_registry_rows:
        artifact_id = str(row.get("table_id", "")).strip()
        temp_destination_path = str(row.get("destination_path", "")).strip()
        destination_filename = str(row.get("destination_filename", "")).strip()
        destination_path = (
            str((run_root / "paper_exports" / "tables" / destination_filename).resolve())
            if destination_filename
            else ""
        )
        source_path = str(row.get("source_path", "")).strip()
        sha = (
            sha256_hex(Path(temp_destination_path).read_bytes())
            if temp_destination_path and Path(temp_destination_path).exists()
            else ""
        )
        latex_name = str(latex_paths.get(artifact_id, "")).strip()
        artifacts_out.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": "table",
                "run_id": str(run_id),
                "source_path": source_path,
                "destination_path": destination_path,
                "sha256": sha,
                "paper_allowed": True,
                "contract_version": str(contract_version),
                "latex_path": (
                    str((run_root / "paper_exports" / "tables_latex" / latex_name).resolve())
                    if latex_name
                    else ""
                ),
            }
        )
    for blocked_id in sorted(blocked_non_paper_ids):
        artifacts_out.append(
            {
                "artifact_id": blocked_id,
                "artifact_type": "blocked_non_paper",
                "run_id": str(run_id),
                "source_path": "",
                "destination_path": "",
                "sha256": "",
                "paper_allowed": False,
                "contract_version": str(contract_version),
            }
        )
    return {
        "run_id": str(run_id),
        "contract_version": str(contract_version),
        "artifacts": sorted(artifacts_out, key=lambda item: str(item.get("artifact_id", ""))),
    }



def validate_paper_export_content(
    *,
    run_id: str,
    run_root: Path,
    diagnostics_dir: Path,
    fig_dir: Path,
    tab_dir: Path,
    top_permissions: int,
    top_families: int,
    min_family_support: int,
    strict_profile: bool,
) -> dict[str, Any]:
    """Validate paper-export artifact shape/content invariants.

    Raises:
        ValueError: If strict mode is enabled and any invariant fails.
    """
    checks: dict[str, Any] = {
        "figures_png_count": 0,
        "tables_csv_count": 0,
        "model_rows": 0,
        "model_set_ok": False,
        "ablation_feature_set_ok": False,
        "temporal_year_scope_ok": False,
        "dangerous_stats_schema_ok": False,
        "jsd_pair_rows": 0,
        "jsd_family_count": 0,
        "selected_visual_family_count": 0,
        "selected_visual_family_support_floor_ok": False,
        "trained_family_support_floor_ok": False,
        "confusion_eval_source_ok": False,
        "confusion_model_ok": False,
        "top_permissions_requested": int(top_permissions),
        "top_families_requested": int(top_families),
        "min_family_support_required": int(min_family_support),
    }

    fig_files = sorted(fig_dir.glob("*.png"))
    tab_files = sorted(tab_dir.glob("*.csv"))
    checks["figures_png_count"] = int(len(fig_files))
    checks["tables_csv_count"] = int(len(tab_files))
    checks["figures_nonzero_ok"] = bool(all(p.exists() and p.stat().st_size > 0 for p in fig_files))
    checks["tables_nonzero_ok"] = bool(all(p.exists() and p.stat().st_size > 0 for p in tab_files))

    model_path = tab_dir / "model_comparison_rf_xgb_lr_fused.csv"
    if model_path.exists():
        model_df = pd.read_csv(model_path)
        checks["model_rows"] = int(len(model_df))
        if not model_df.empty and {"model", "macro_f1", "accuracy"}.issubset(model_df.columns):
            model_set = set(model_df["model"].astype(str).tolist())
            checks["model_set_ok"] = bool(
                model_set == {"random_forest", "xgboost", "logistic_regression"}
                and len(model_df) == 3
            )

    ablation_path = tab_dir / "feature_ablation.csv"
    if ablation_path.exists():
        abl_df = pd.read_csv(ablation_path)
        if not abl_df.empty and {"feature_set", "model"}.issubset(abl_df.columns):
            feature_set = set(abl_df["feature_set"].astype(str).tolist())
            model_set = set(abl_df["model"].astype(str).tolist())
            checks["ablation_feature_set_ok"] = bool(
                feature_set == {"permissions_only", "vendor_only", "vendor_permissions_fused"}
                and model_set.issubset({"random_forest", "xgboost", "logistic_regression"})
                and len(model_set) > 0
            )

    temporal_path = tab_dir / "malware_family_temporal_scope.csv"
    if temporal_path.exists():
        temp_df = pd.read_csv(temporal_path)
        if not temp_df.empty and {"first_seen", "last_seen"}.issubset(temp_df.columns):
            years = pd.concat(
                [
                    pd.to_datetime(temp_df["first_seen"], errors="coerce", utc=True).dt.year,
                    pd.to_datetime(temp_df["last_seen"], errors="coerce", utc=True).dt.year,
                ],
                ignore_index=True,
            )
            years = years.dropna().astype(int)
            if years.empty:
                checks["temporal_year_scope_ok"] = True
            else:
                checks["temporal_year_scope_ok"] = bool(((years >= 2020) & (years <= 2025)).all())

    dangerous_path = tab_dir / "dangerous_permission_stats_tests.csv"
    if dangerous_path.exists():
        dangerous_df = pd.read_csv(dangerous_path)
        checks["dangerous_stats_schema_ok"] = bool(
            not dangerous_df.empty
            and "metric" in dangerous_df.columns
            and (
                "p_value" in dangerous_df.columns
                or "pvalue" in dangerous_df.columns
                or "p-value" in dangerous_df.columns
            )
        )

    jsd_pairs_path = diagnostics_dir / f"family_jsd_pairs_verification_{run_id}.csv"
    if jsd_pairs_path.exists():
        jsd_df = pd.read_csv(jsd_pairs_path)
        checks["jsd_pair_rows"] = int(len(jsd_df))
        if {"family_a", "family_b"}.issubset(jsd_df.columns):
            fams = set(jsd_df["family_a"].astype(str).tolist()) | set(jsd_df["family_b"].astype(str).tolist())
            checks["jsd_family_count"] = int(len([f for f in fams if str(f).strip()]))

    selected_path = diagnostics_dir / f"selected_families_visual_{run_id}.csv"
    if selected_path.exists():
        selected_df = pd.read_csv(selected_path)
        checks["selected_visual_family_count"] = int(len(selected_df))
        if "sample_count" in selected_df.columns:
            work = selected_df.copy()
            work["sample_count"] = pd.to_numeric(work["sample_count"], errors="coerce").fillna(0).astype(int)
            if "included_in_visual" in work.columns:
                included = work[
                    pd.to_numeric(work["included_in_visual"], errors="coerce").fillna(0).astype(int) == 1
                ]
            else:
                included = work
            if not included.empty:
                checks["selected_visual_family_support_floor_ok"] = bool(
                    (included["sample_count"] >= max(min_family_support, 1)).all()
                )

    trained_path = diagnostics_dir / f"trained_family_registry_{run_id}.csv"
    if trained_path.exists():
        trained_df = pd.read_csv(trained_path)
        if {"sample_count", "included_in_training"}.issubset(trained_df.columns):
            work = trained_df.copy()
            work["sample_count"] = pd.to_numeric(work["sample_count"], errors="coerce").fillna(0).astype(int)
            included = work[pd.to_numeric(work["included_in_training"], errors="coerce").fillna(0).astype(int) == 1]
            checks["trained_family_support_floor_ok"] = bool(
                not included.empty and (included["sample_count"] >= max(min_family_support, 1)).all()
            )

    confusion_path = diagnostics_dir / f"confusion_matrix_provenance_{run_id}.csv"
    if confusion_path.exists():
        conf_df = pd.read_csv(confusion_path)
        if not conf_df.empty:
            checks["confusion_eval_source_ok"] = bool(
                "eval_source" in conf_df.columns
                and conf_df["eval_source"].astype(str).str.lower().eq("test_set").all()
            )
            checks["confusion_model_ok"] = bool(
                "model_name" in conf_df.columns
                and conf_df["model_name"].astype(str).str.lower().eq("random_forest").all()
            )

    required_true = [
        "figures_nonzero_ok",
        "tables_nonzero_ok",
        "model_set_ok",
        "ablation_feature_set_ok",
        "temporal_year_scope_ok",
        "dangerous_stats_schema_ok",
        "selected_visual_family_support_floor_ok",
        "trained_family_support_floor_ok",
        "confusion_eval_source_ok",
        "confusion_model_ok",
    ]
    if strict_profile:
        failures = [key for key in required_true if not bool(checks.get(key, False))]
        if checks.get("figures_png_count", 0) != 5:
            failures.append("figures_png_count")
        if checks.get("tables_csv_count", 0) != 5:
            failures.append("tables_csv_count")
        if checks.get("jsd_pair_rows", 0) != (int(top_families) * (int(top_families) - 1)) // 2:
            failures.append("jsd_pair_rows")
        if checks.get("jsd_family_count", 0) != int(top_families):
            failures.append("jsd_family_count")
        if checks.get("selected_visual_family_count", 0) != int(top_families):
            failures.append("selected_visual_family_count")
        if failures:
            raise ValueError(
                "[PAPER2] Strict export content validation failed: "
                + ", ".join(sorted(set(failures)))
            )
    return checks



def build_paper_ablation_table(*, source_path: Path, output_path: Path) -> None:
    """Build compact ablation table restricted to locked feature sets/models."""
    src_df = pd.read_csv(source_path)
    if src_df.empty:
        pd.DataFrame(columns=["feature_set", "model", "macro_f1", "accuracy", "delta_vs_vendoronly"]).to_csv(
            output_path,
            index=False,
        )
        return
    feature_col = (
        "Feature Set"
        if "Feature Set" in src_df.columns
        else ("feature_set" if "feature_set" in src_df.columns else ("experiment" if "experiment" in src_df.columns else ""))
    )
    model_col = "Model" if "Model" in src_df.columns else ("model" if "model" in src_df.columns else "")
    macro_col = (
        "MacroF1"
        if "MacroF1" in src_df.columns
        else ("macro_f1" if "macro_f1" in src_df.columns else ("macro_f1_score" if "macro_f1_score" in src_df.columns else ""))
    )
    acc_col = "accuracy" if "accuracy" in src_df.columns else ("Acc" if "Acc" in src_df.columns else "")
    delta_col = (
        "Delta vs VendorOnly"
        if "Delta vs VendorOnly" in src_df.columns
        else ("delta_vs_vendoronly" if "delta_vs_vendoronly" in src_df.columns else ("leakage_sensitivity_delta" if "leakage_sensitivity_delta" in src_df.columns else ""))
    )
    if not feature_col or not model_col or not macro_col:
        src_df.to_csv(output_path, index=False)
        return
    keep_features = {"permissions_only", "vendor_only", "vendor_permissions_fused"}
    model_map = {
        "rf": "random_forest",
        "random_forest": "random_forest",
        "xgb": "xgboost",
        "xgboost": "xgboost",
        "log_reg": "logistic_regression",
        "logistic_regression": "logistic_regression",
    }
    work = src_df[[feature_col, model_col, macro_col]].copy()
    work["feature_set"] = work[feature_col].astype(str).str.strip().str.lower()
    work["model"] = work[model_col].astype(str).str.strip().str.lower().map(model_map)
    work["accuracy"] = pd.to_numeric(src_df[acc_col], errors="coerce") if acc_col else np.nan
    work["delta_vs_vendoronly"] = pd.to_numeric(src_df[delta_col], errors="coerce") if delta_col else np.nan
    work = work[
        work["feature_set"].isin(keep_features)
        & work["model"].isin({"random_forest", "xgboost", "logistic_regression"})
    ].copy()
    work["macro_f1"] = pd.to_numeric(work[macro_col], errors="coerce")
    feature_order = {"permissions_only": 0, "vendor_only": 1, "vendor_permissions_fused": 2}
    model_order = {"random_forest": 0, "xgboost": 1, "logistic_regression": 2}
    work["f_order"] = work["feature_set"].map(feature_order).fillna(99).astype(int)
    work["m_order"] = work["model"].map(model_order).fillna(99).astype(int)
    out = work.sort_values(by=["f_order", "m_order"], ascending=[True, True], kind="mergesort")[
        ["feature_set", "model", "macro_f1", "accuracy", "delta_vs_vendoronly"]
    ]
    out.to_csv(output_path, index=False, float_format="%.6f")



def build_paper_cohort_summary_table(*, samples_df: pd.DataFrame | None, run_id: str) -> pd.DataFrame:
    """Build paper cohort summary table."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return pd.DataFrame(
            [
                {
                    "run_id": str(run_id),
                    "type_slug": "",
                    "family_count": 0,
                    "sample_count": 0,
                    "pct_of_dataset": 0.0,
                    "total_samples": 0,
                    "unique_families": 0,
                    "unique_types": 0,
                    "top_family_share": 0.0,
                    "banker_share": 0.0,
                }
            ]
        )
    work = samples_df.copy()
    work["type_slug"] = work.get("type_slug", "").fillna("").astype(str).str.strip().str.lower()
    work["family_canonical"] = work.get("family_canonical", "").fillna("").astype(str).str.strip()
    total = max(int(len(work)), 1)
    grouped = (
        work.groupby("type_slug", as_index=False)
        .agg(
            family_count=("family_canonical", lambda s: int(s[s.astype(str).str.strip() != ""].nunique())),
            sample_count=("type_slug", "size"),
        )
        .sort_values(by=["sample_count", "type_slug"], ascending=[False, True], kind="mergesort")
    )
    grouped["pct_of_dataset"] = (grouped["sample_count"] / total).round(6)
    total_samples = int(len(work))
    unique_families = int(work.loc[work["family_canonical"] != "", "family_canonical"].nunique())
    unique_types = int(work.loc[work["type_slug"] != "", "type_slug"].nunique())
    family_counts = (
        work.loc[work["family_canonical"] != "", "family_canonical"]
        .value_counts(dropna=True)
        .astype(int)
    )
    top_family_share = round(float(family_counts.max()) / float(total), 6) if not family_counts.empty else 0.0
    banker_share = round(float((work["type_slug"] == "banker").sum()) / float(total), 6)
    grouped["total_samples"] = total_samples
    grouped["unique_families"] = unique_families
    grouped["unique_types"] = unique_types
    grouped["top_family_share"] = top_family_share
    grouped["banker_share"] = banker_share
    grouped.insert(0, "run_id", str(run_id))
    return grouped.reset_index(drop=True)



def build_family_temporal_scope_table(*, samples_df: pd.DataFrame | None, run_id: str) -> pd.DataFrame:
    """Build family/type temporal scope table with first/last seen years."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return pd.DataFrame(
            columns=[
                "run_id",
                "family_canonical",
                "type_slug",
                "first_seen",
                "last_seen",
                "sample_count",
            ]
        )
    work = samples_df.copy()
    work["family_canonical"] = work.get("family_canonical", "").fillna("").astype(str).str.strip()
    work["type_slug"] = work.get("type_slug", "").fillna("").astype(str).str.strip().str.lower()
    work = work[work["family_canonical"] != ""].copy()
    if work.empty:
        return pd.DataFrame(
            columns=[
                "run_id",
                "family_canonical",
                "type_slug",
                "first_seen",
                "last_seen",
                "sample_count",
            ]
        )
    effective = pd.to_datetime(
        work["effective_first_seen_at_utc"]
        if "effective_first_seen_at_utc" in work.columns
        else pd.Series(pd.NaT, index=work.index),
        errors="coerce",
        utc=True,
    )
    itw = pd.to_datetime(
        work["vt_first_seen_itw_date"]
        if "vt_first_seen_itw_date" in work.columns
        else pd.Series(pd.NaT, index=work.index),
        errors="coerce",
        utc=True,
    )
    sub = pd.to_datetime(
        work["vt_first_submission_at_utc"]
        if "vt_first_submission_at_utc" in work.columns
        else pd.Series(pd.NaT, index=work.index),
        errors="coerce",
        utc=True,
    )
    work["time_anchor"] = effective.where(effective.notna(), itw.where(itw.notna(), sub))
    grouped = (
        work.groupby(["family_canonical", "type_slug"], as_index=False)
        .agg(
            first_seen=("time_anchor", "min"),
            last_seen=("time_anchor", "max"),
            sample_count=("family_canonical", "size"),
        )
        .sort_values(by=["sample_count", "family_canonical"], ascending=[False, True], kind="mergesort")
    )
    grouped["first_seen"] = pd.to_datetime(grouped["first_seen"], errors="coerce", utc=True).dt.date.astype(str)
    grouped["last_seen"] = pd.to_datetime(grouped["last_seen"], errors="coerce", utc=True).dt.date.astype(str)
    grouped.insert(0, "run_id", str(run_id))
    return grouped.reset_index(drop=True)


def build_strict_paper2_exports(
    *,
    run_root: Path,
    diagnostics_dir: Path,
    run_id: str,
    samples_df: pd.DataFrame | None,
    manifest_context: dict[str, Any],
    evidence_mode: bool,
    paper_mode: bool,
) -> dict[str, Any]:
    """Build strict Paper #2 export set and fail on missing locked artifacts."""
    paper_exports_root = run_root / "paper_exports"
    if not bool(paper_mode):
        if paper_exports_root.exists():
            shutil.rmtree(paper_exports_root)
            du.print_info("[PAPER2] Removed stale paper_exports (paper mode OFF).")
        du.print_info("[PAPER2] Strict paper export skipped (paper mode OFF).")
        return {
            "profile": {
                "enabled": False,
                "reason": "paper_mode_disabled",
                "single_run_id": str(run_id),
            },
            "artifact_paths": [],
        }
    strict_profile = bool(getattr(app_config, "PAPER2_STRICT_EXPORT_PROFILE", True)) and bool(paper_mode)
    contract_version = "paper2.v2"
    temp_export_root = run_root / f"paper_exports.__tmp__{uuid4().hex[:8]}"
    if temp_export_root.exists():
        shutil.rmtree(temp_export_root, ignore_errors=True)

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

    bundle_dir = run_root / "bundles" / "permission_trends"
    figure_sources: dict[str, Path] = {}
    conf_rf = find_primary_confusion_matrix(
        run_root=run_root,
        top_model="random_forest",
        evidence_mode=True if evidence_mode else False,
    )
    if conf_rf is not None:
        figure_sources["fig5_confusion_matrix_random_forest"] = conf_rf

    table_sources = {
        "table3_model_comparison_rf_xgb_lr_fused": diagnostics_dir / f"model_comparison_summary_{run_id}.csv",
        "table4_feature_ablation": diagnostics_dir / "ablation_summary.csv",
        "table5_dangerous_permission_stats_tests": bundle_dir / "tables" / "dangerous_stats_tests.latest.csv",
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

    type_prev_csv = bundle_dir / "tables" / "type_permission_prevalence.latest.csv"
    discrim_csv = bundle_dir / "tables" / "permission_discriminability_rank.latest.csv"
    dangerous_csv = bundle_dir / "tables" / "dangerous_distribution_by_type.latest.csv"
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

    missing: list[str] = []
    for logical, path in required_sources.items():
        if path is None or not Path(path).exists():
            missing.append(logical)
    if missing and strict_profile:
        raise ValueError(
            "[PAPER2] Strict paper export failed; missing required artifacts: "
            + ", ".join(sorted(missing))
        )
    exported_paths: list[str] = []
    figure_registry_rows: list[dict[str, Any]] = []
    table_registry_rows: list[dict[str, Any]] = []
    figure_inputs: dict[str, list[str]] = {}
    table_inputs: dict[str, list[str]] = {}
    validation_summary: dict[str, Any] = {}
    try:
        fig_dir = temp_export_root / "figures"
        tab_dir = temp_export_root / "tables"
        latex_dir = temp_export_root / "tables_latex"
        docs_dir = temp_export_root / "docs"
        fig_dir.mkdir(parents=True, exist_ok=True)
        tab_dir.mkdir(parents=True, exist_ok=True)
        latex_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.mkdir(parents=True, exist_ok=True)

        # Figure 1: deterministic pipeline architecture figure generated for paper exports.
        fig1_id = "fig1_pipeline_architecture"
        fig1_path = fig_dir / figure_filename_map[fig1_id]
        render_pipeline_architecture_figure(output_path=fig1_path)
        exported_paths.append(str(fig1_path))
        figure_registry_rows.append(
            {
                "run_id": str(run_id),
                "contract_version": contract_version,
                "figure_id": fig1_id,
                "destination_filename": fig1_path.name,
                "destination_path": str((run_root / "paper_exports" / "figures" / fig1_path.name).resolve()),
                "source_path": "",
                "source_stage": figure_stage_map.get(fig1_id, "unknown"),
                "qc_status": "pass",
                "notes": "generated",
            }
        )
        figure_inputs[fig1_id] = []

        for figure_id, src in figure_sources.items():
            src_path = Path(src)
            if not src_path.exists():
                continue
            if run_root.resolve() not in src_path.resolve().parents:
                raise ValueError(f"[PAPER2] Non run-scoped source rejected: {src_path}")
            dst = fig_dir / figure_filename_map[figure_id]
            shutil.copy2(src_path, dst)
            exported_paths.append(str(dst))
            figure_registry_rows.append(
                {
                    "run_id": str(run_id),
                    "contract_version": contract_version,
                    "figure_id": figure_id,
                    "destination_filename": dst.name,
                    "destination_path": str((run_root / "paper_exports" / "figures" / dst.name).resolve()),
                    "source_path": str(src_path.resolve()),
                    "source_stage": figure_stage_map.get(figure_id, "unknown"),
                    "qc_status": "pass",
                    "notes": "copied",
                }
            )
            figure_inputs[figure_id] = [str(src_path.resolve())]

        conf_dst = fig_dir / figure_filename_map["fig5_confusion_matrix_random_forest"]
        annotate_confusion_matrix_with_metrics(
            confusion_path=conf_dst,
            model_comparison_csv=diagnostics_dir / f"model_comparison_summary_{run_id}.csv",
        )

        # Re-render key paper figures from run-scoped tables for publication readability.
        render_paper_type_heatmap_from_table(
            type_prevalence_path=type_prev_csv,
            discriminability_path=discrim_csv,
            output_path=fig_dir / figure_filename_map["fig2_type_permission_heatmap"],
            top_permissions=safe_int_config_value(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 16), default=16),
        )
        render_paper_dangerous_distribution_from_table(
            dangerous_distribution_path=dangerous_csv,
            output_path=fig_dir / figure_filename_map["fig3_dangerous_permission_distribution_by_type"],
        )
        render_paper_jsd_heatmap_from_pairs(
            jsd_pair_path=jsd_pairs_csv,
            output_path=fig_dir / figure_filename_map["fig4_family_jsd_heatmap_top12"],
        )
        for figure_id, source_paths in {
            "fig2_type_permission_heatmap": [type_prev_csv, discrim_csv],
            "fig3_dangerous_permission_distribution_by_type": [dangerous_csv],
            "fig4_family_jsd_heatmap_top12": [jsd_pairs_csv],
        }.items():
            rendered_dst = fig_dir / figure_filename_map[figure_id]
            figure_registry_rows.append(
                {
                    "run_id": str(run_id),
                    "contract_version": contract_version,
                    "figure_id": figure_id,
                    "destination_filename": rendered_dst.name,
                    "destination_path": str((run_root / "paper_exports" / "figures" / rendered_dst.name).resolve()),
                    "source_path": ";".join([str(Path(p).resolve()) for p in source_paths]),
                    "source_stage": figure_stage_map.get(figure_id, "unknown"),
                    "qc_status": "pass",
                    "notes": "rendered_from_tables",
                }
            )
            if str(rendered_dst) not in exported_paths:
                exported_paths.append(str(rendered_dst))
        figure_inputs["fig2_type_permission_heatmap"] = [str(type_prev_csv.resolve()), str(discrim_csv.resolve())]
        figure_inputs["fig3_dangerous_permission_distribution_by_type"] = [str(dangerous_csv.resolve())]
        figure_inputs["fig4_family_jsd_heatmap_top12"] = [str(jsd_pairs_csv.resolve())]

        cohort_id = "table1_cohort_summary"
        cohort_summary_path = tab_dir / table_filename_map[cohort_id]
        cohort_summary_df = build_paper_cohort_summary_table(samples_df=samples_df, run_id=run_id)
        cohort_summary_df.to_csv(cohort_summary_path, index=False)
        exported_paths.append(str(cohort_summary_path))
        table_registry_rows.append(
            {
                "run_id": str(run_id),
                "contract_version": contract_version,
                "table_id": cohort_id,
                "destination_filename": cohort_summary_path.name,
                "destination_path": str((run_root / "paper_exports" / "tables" / cohort_summary_path.name).resolve()),
                "source_path": "",
                "source_stage": table_stage_map.get(cohort_id, "unknown"),
                "qc_status": "pass",
                "notes": "generated",
            }
        )
        table_inputs[cohort_id] = []

        temporal_id = "table2_malware_family_temporal_scope"
        temporal_path = tab_dir / table_filename_map[temporal_id]
        temporal_df = build_family_temporal_scope_table(samples_df=samples_df, run_id=run_id)
        temporal_df.to_csv(temporal_path, index=False)
        exported_paths.append(str(temporal_path))
        table_registry_rows.append(
            {
                "run_id": str(run_id),
                "contract_version": contract_version,
                "table_id": temporal_id,
                "destination_filename": temporal_path.name,
                "destination_path": str((run_root / "paper_exports" / "tables" / temporal_path.name).resolve()),
                "source_path": "",
                "source_stage": table_stage_map.get(temporal_id, "unknown"),
                "qc_status": "pass",
                "notes": "generated",
            }
        )
        table_inputs[temporal_id] = []

        temporal_provenance_path = docs_dir / "temporal_timestamp_provenance.json"
        temporal_provenance_payload = {
            "run_id": str(run_id),
            "timestamp_field": "effective_first_seen_at_utc",
            "timestamp_priority_chain": [
                "effective_first_seen_at_utc",
                "vt_first_seen_itw_date",
                "vt_first_submission_at_utc",
            ],
            "source_contract_path": str(oh.resolve_dataset_time_contract_path(diagnostics_dir, str(run_id))),
        }
        temporal_provenance_path.write_text(
            json.dumps(temporal_provenance_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        exported_paths.append(str(temporal_provenance_path))

        for table_id, src in table_sources.items():
            src_path = Path(src)
            if not src_path.exists():
                continue
            if run_root.resolve() not in src_path.resolve().parents:
                raise ValueError(f"[PAPER2] Non run-scoped source rejected: {src_path}")
            dst = tab_dir / table_filename_map[table_id]
            if table_id == "table3_model_comparison_rf_xgb_lr_fused":
                build_paper_model_comparison_table(source_path=src_path, output_path=dst)
            elif table_id == "table4_feature_ablation":
                build_paper_ablation_table(source_path=src_path, output_path=dst)
            else:
                shutil.copy2(src_path, dst)
            exported_paths.append(str(dst))
            table_registry_rows.append(
                {
                    "run_id": str(run_id),
                    "contract_version": contract_version,
                    "table_id": table_id,
                    "destination_filename": dst.name,
                    "destination_path": str((run_root / "paper_exports" / "tables" / dst.name).resolve()),
                    "source_path": str(src_path.resolve()),
                    "source_stage": table_stage_map.get(table_id, "unknown"),
                    "qc_status": "pass",
                    "notes": "generated_from_source" if table_id != "table5_dangerous_permission_stats_tests" else "copied",
                }
            )
            table_inputs[table_id] = [str(src_path.resolve())]

        seen_figures = {str(row.get("figure_id", "")) for row in figure_registry_rows}
        seen_tables = {str(row.get("table_id", "")) for row in table_registry_rows}
        if strict_profile and (seen_figures != required_figure_ids or seen_tables != required_table_ids):
            missing_figures = sorted(required_figure_ids - seen_figures)
            extra_figures = sorted(seen_figures - required_figure_ids)
            missing_tables = sorted(required_table_ids - seen_tables)
            extra_tables = sorted(seen_tables - required_table_ids)
            raise ValueError(
                "[PAPER2] Strict export contract violation: "
                f"missing_figures={missing_figures}, extra_figures={extra_figures}, "
                f"missing_tables={missing_tables}, extra_tables={extra_tables}"
            )

        validation_summary = validate_paper_export_content(
            run_id=run_id,
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            fig_dir=fig_dir,
            tab_dir=tab_dir,
            top_permissions=safe_int_config_value(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 16), default=16),
            top_families=safe_int_config_value(getattr(app_config, "MAX_FAMILY_VISUAL_COUNT", 12), default=12),
            min_family_support=safe_int_config_value(getattr(app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 20), default=20),
            strict_profile=strict_profile,
        )

        figure_registry_path = docs_dir / "paper_figure_registry.csv"
        pd.DataFrame(figure_registry_rows).to_csv(figure_registry_path, index=False)
        exported_paths.append(str(figure_registry_path))

        table_registry_path = docs_dir / "paper_table_registry.csv"
        pd.DataFrame(table_registry_rows).to_csv(table_registry_path, index=False)
        exported_paths.append(str(table_registry_path))

        latex_paths: dict[str, str] = {}
        for table_id in sorted(required_table_ids):
            csv_name = table_filename_map[table_id]
            csv_path = tab_dir / csv_name
            tex_path = latex_dir / f"{Path(csv_name).stem}.tex"
            write_table_latex_from_csv(csv_path=csv_path, tex_path=tex_path)
            exported_paths.append(str(tex_path))
            latex_paths[table_id] = tex_path.name

        profile_payload = {
            "strict_profile_enabled": strict_profile,
            "single_run_id": str(run_id),
            "visual_family_support_threshold": safe_int_config_value(getattr(app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 20), default=20),
            "top_families_visual": safe_int_config_value(getattr(app_config, "MAX_FAMILY_VISUAL_COUNT", 12), default=12),
            "top_permissions": safe_int_config_value(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 16), default=16),
            "paper_export_contract_version": contract_version,
        }
        profile_path = docs_dir / "paper_export_profile.json"
        profile_path.write_text(json.dumps(profile_payload, indent=2, sort_keys=True), encoding="utf-8")
        exported_paths.append(str(profile_path))

        figure_qc_path = docs_dir / "paper_figure_qc.csv"
        export_paper_figure_qc(fig_dir=fig_dir, output_path=figure_qc_path)
        exported_paths.append(str(figure_qc_path))

        paper_registry_path = docs_dir / "paper_registry.json"
        paper_registry_payload = build_paper_registry_payload(
            run_root=run_root,
            run_id=run_id,
            contract_version=contract_version,
            figure_registry_rows=figure_registry_rows,
            table_registry_rows=table_registry_rows,
            latex_paths=latex_paths,
            blocked_non_paper_ids=blocked_non_paper_ids,
        )
        paper_registry_path.write_text(
            json.dumps(paper_registry_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        exported_paths.append(str(paper_registry_path))

        export_manifest_path = docs_dir / "paper_exports_manifest.json"
        export_manifest_payload = {
            "run_id": str(run_id),
            "contract_version": contract_version,
            "strict_profile_enabled": bool(strict_profile),
            "run_mode": "paper",
            "figure_ids": sorted([str(row.get("figure_id", "")) for row in figure_registry_rows]),
            "table_ids": sorted([str(row.get("table_id", "")) for row in table_registry_rows]),
            "figure_registry_csv": str(figure_registry_path.resolve()),
            "table_registry_csv": str(table_registry_path.resolve()),
            "paper_export_profile_json": str(profile_path.resolve()),
            "paper_registry_json": str(paper_registry_path.resolve()),
            "tables_latex_dir": str(latex_dir.resolve()),
            "figure_sources": figure_inputs,
            "table_sources": table_inputs,
            "validation_summary": validation_summary,
        }
        export_manifest_path.write_text(
            json.dumps(export_manifest_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        exported_paths.append(str(export_manifest_path))

        if paper_exports_root.exists():
            shutil.rmtree(paper_exports_root)
        temp_export_root.replace(paper_exports_root)
    except Exception:
        if temp_export_root.exists():
            shutil.rmtree(temp_export_root, ignore_errors=True)
        if paper_exports_root.exists():
            shutil.rmtree(paper_exports_root, ignore_errors=True)
        raise

    return {
        "profile": {
            "strict_profile_enabled": strict_profile,
            "single_run_id": str(run_id),
            "visual_family_support_threshold": safe_int_config_value(getattr(app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 20), default=20),
            "top_families_visual": safe_int_config_value(getattr(app_config, "MAX_FAMILY_VISUAL_COUNT", 12), default=12),
            "top_permissions": safe_int_config_value(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 16), default=16),
            "paper_export_contract_version": contract_version,
        },
        "artifact_paths": sorted(set([str(Path(path).resolve()) for path in exported_paths])),
    }


