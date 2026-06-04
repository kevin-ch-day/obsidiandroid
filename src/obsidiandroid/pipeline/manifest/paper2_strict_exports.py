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
from obsidiandroid.pipeline.manifest.paper_evidence import (
    build_manuscript_table_constants,
    validate_paper_contract_bundle,
    write_feature_set_glossary,
    write_manuscript_table_constants,
    write_perturbation_summary,
)
from obsidiandroid.pipeline.manifest.paper_export_contracts import (
    build_paper_export_contract,
    missing_required_paper_sources,
)
from obsidiandroid.pipeline.manifest.paper_export_paths import (
    build_paper_export_settings,
    build_paper_docs_paths,
    build_paper_export_profile_payload,
    build_paper_exports_manifest_payload,
)
from obsidiandroid.pipeline.manifest.paper_export_registry import build_paper_registry_payload
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
                "[EXPORT] Strict publication export content validation failed: "
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
    feature_aliases = {
        "permissions_only": "permissions_only",
        "permissions_grouped": "permissions_only",
        "permissions_raw": "permissions_only",
        "vendor_only": "vendor_only",
        "vendor_no_parsed_family": "vendor_only",
        "vendor_permissions_fused": "vendor_permissions_fused",
        "permissions_grouped_plus_vendor_no_family": "vendor_permissions_fused",
        "permissions_grouped_plus_vendor_safe": "vendor_permissions_fused",
    }
    model_map = {
        "rf": "random_forest",
        "random_forest": "random_forest",
        "xgb": "xgboost",
        "xgboost": "xgboost",
        "log_reg": "logistic_regression",
        "logistic_regression": "logistic_regression",
    }
    work = src_df[[feature_col, model_col, macro_col]].copy()
    if "label_target" in src_df.columns:
        work["label_target"] = src_df["label_target"].astype(str).str.strip().str.lower()
    else:
        work["label_target"] = ""
    work["feature_set"] = (
        work[feature_col].astype(str).str.strip().str.lower().map(feature_aliases).fillna("")
    )
    work["model"] = work[model_col].astype(str).str.strip().str.lower().map(model_map)
    work["accuracy"] = pd.to_numeric(src_df[acc_col], errors="coerce") if acc_col else np.nan
    work["delta_vs_vendoronly"] = pd.to_numeric(src_df[delta_col], errors="coerce") if delta_col else np.nan
    work = work[
        work["feature_set"].isin(keep_features)
        & work["model"].isin({"random_forest", "xgboost", "logistic_regression"})
    ].copy()
    work["macro_f1"] = pd.to_numeric(work[macro_col], errors="coerce")
    label_target_order = {
        "family_id": 0,
        "family_canonical_default": 1,
        "family_within_type": 2,
        "type_slug": 3,
        "": 4,
    }
    feature_order = {"permissions_only": 0, "vendor_only": 1, "vendor_permissions_fused": 2}
    model_order = {"random_forest": 0, "xgboost": 1, "logistic_regression": 2}
    work["label_order"] = work["label_target"].map(label_target_order).fillna(99).astype(int)
    work["f_order"] = work["feature_set"].map(feature_order).fillna(99).astype(int)
    work["m_order"] = work["model"].map(model_order).fillna(99).astype(int)
    out = (
        work.sort_values(
            by=["label_order", "f_order", "m_order"],
            ascending=[True, True, True],
            kind="mergesort",
        )
        .drop_duplicates(subset=["feature_set", "model"], keep="first")
    )[
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
    manifest: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    evidence_mode: bool,
    paper_mode: bool,
) -> dict[str, Any]:
    """Build strict Paper #2 export set and fail on missing locked artifacts."""
    paper_exports_root = run_root / "paper_exports"
    if not bool(paper_mode):
        if paper_exports_root.exists():
            shutil.rmtree(paper_exports_root)
            du.print_info("[EXPORT] Removed stale strict publication exports (evidence/publication mode OFF).")
        du.print_info("[EXPORT] Strict publication export skipped (evidence/publication mode OFF).")
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

    export_contract = build_paper_export_contract(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        evidence_mode=evidence_mode,
    )
    required_figure_ids = export_contract["required_figure_ids"]
    required_table_ids = export_contract["required_table_ids"]
    blocked_non_paper_ids = export_contract["blocked_non_paper_ids"]
    figure_filename_map = export_contract["figure_filename_map"]
    table_filename_map = export_contract["table_filename_map"]
    figure_stage_map = export_contract["figure_stage_map"]
    table_stage_map = export_contract["table_stage_map"]
    figure_sources = export_contract["figure_sources"]
    table_sources = export_contract["table_sources"]
    type_prev_csv = export_contract["type_prevalence_csv"]
    discrim_csv = export_contract["permission_discriminability_csv"]
    dangerous_csv = export_contract["dangerous_distribution_csv"]
    jsd_pairs_csv = export_contract["family_jsd_pairs_csv"]

    missing = missing_required_paper_sources(export_contract["required_sources"])
    if missing and strict_profile:
        raise ValueError(
            "[EXPORT] Strict publication export failed; missing required artifacts: "
            + ", ".join(sorted(missing))
        )
    exported_paths: list[str] = []
    figure_registry_rows: list[dict[str, Any]] = []
    table_registry_rows: list[dict[str, Any]] = []
    figure_inputs: dict[str, list[str]] = {}
    table_inputs: dict[str, list[str]] = {}
    validation_summary: dict[str, Any] = {}
    export_settings = build_paper_export_settings(app_config_obj=app_config)
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
                raise ValueError(f"[EXPORT] Non run-scoped source rejected: {src_path}")
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
            top_permissions=export_settings["top_permissions"],
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
                raise ValueError(f"[EXPORT] Non run-scoped source rejected: {src_path}")
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
                "[EXPORT] Strict publication export contract violation: "
                f"missing_figures={missing_figures}, extra_figures={extra_figures}, "
                f"missing_tables={missing_tables}, extra_tables={extra_tables}"
            )

        validation_summary = validate_paper_export_content(
            run_id=run_id,
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            fig_dir=fig_dir,
            tab_dir=tab_dir,
            top_permissions=export_settings["top_permissions"],
            top_families=export_settings["top_families_visual"],
            min_family_support=export_settings["visual_family_support_threshold"],
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

        docs_paths = build_paper_docs_paths(docs_dir=docs_dir)
        profile_payload = build_paper_export_profile_payload(
            strict_profile=strict_profile,
            run_id=run_id,
            contract_version=contract_version,
            visual_family_support_threshold=export_settings["visual_family_support_threshold"],
            top_families_visual=export_settings["top_families_visual"],
            top_permissions=export_settings["top_permissions"],
            docs_paths=docs_paths,
        )
        profile_path = docs_paths["paper_export_profile_json"]
        profile_path.write_text(json.dumps(profile_payload, indent=2, sort_keys=True), encoding="utf-8")
        exported_paths.append(str(profile_path))

        cohort_contract = {}
        if isinstance(manifest, dict):
            maybe_contract = manifest.get("cohort_contract")
            if isinstance(maybe_contract, dict):
                cohort_contract = maybe_contract
        if not cohort_contract and isinstance(manifest_context, dict):
            maybe_contract = manifest_context.get("paper_cohort_contract")
            if isinstance(maybe_contract, dict):
                cohort_contract = maybe_contract

        manuscript_constants_path = docs_paths["manuscript_table_constants_json"]
        manuscript_constants_payload = build_manuscript_table_constants(
            run_id=run_id,
            profile_id=str((profile or {}).get("profile_id", "unknown")),
            samples_df=samples_df,
            cohort_contract=cohort_contract,
        )
        write_manuscript_table_constants(
            output_path=manuscript_constants_path,
            payload=manuscript_constants_payload,
        )
        exported_paths.append(str(manuscript_constants_path))

        glossary_json_path, glossary_md_path = write_feature_set_glossary(
            json_path=docs_paths["feature_set_glossary_json"],
            md_path=docs_paths["feature_set_glossary_md"],
        )
        exported_paths.extend([str(glossary_json_path), str(glossary_md_path)])

        perturbation_paths = write_perturbation_summary(
            docs_dir=docs_dir,
            runs_root=run_root.parent,
            current_run_root=run_root,
            profile=profile or {},
            manifest=manifest or {},
        )
        exported_paths.extend(str(path) for path in perturbation_paths.values())

        contract_validation = None
        contract_validation_path = docs_paths["paper_contract_validation_json"]
        paper_constants_raw = str(
            (manifest or {}).get("paper_constants_path", "")
            or manifest_context.get("paper_constants_path", "")
            or ""
        ).strip()
        paper_constants_path = Path(paper_constants_raw) if paper_constants_raw else None
        if paper_constants_path is not None and paper_constants_path.exists():
            contract_validation = validate_paper_contract_bundle(
                profile=profile or {},
                manifest=manifest or {},
                paper_constants_path=paper_constants_path,
                manuscript_constants_path=manuscript_constants_path,
            )
            contract_validation_path.write_text(
                json.dumps(contract_validation, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            exported_paths.append(str(contract_validation_path))
            if strict_profile and not bool(contract_validation.get("passed", False)):
                raise ValueError("[EXPORT] strict publication contract validation failed")

        figure_qc_path = docs_paths["paper_figure_qc_csv"]
        export_paper_figure_qc(fig_dir=fig_dir, output_path=figure_qc_path)
        exported_paths.append(str(figure_qc_path))

        paper_registry_path = docs_paths["paper_registry_json"]
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

        export_manifest_path = docs_paths["paper_exports_manifest_json"]
        export_manifest_payload = build_paper_exports_manifest_payload(
            run_id=run_id,
            contract_version=contract_version,
            strict_profile=strict_profile,
            figure_registry_path=figure_registry_path,
            table_registry_path=table_registry_path,
            profile_path=profile_path,
            paper_registry_path=paper_registry_path,
            latex_dir=latex_dir,
            figure_registry_rows=figure_registry_rows,
            table_registry_rows=table_registry_rows,
            figure_inputs=figure_inputs,
            table_inputs=table_inputs,
            docs_paths=docs_paths,
            validation_summary=validation_summary,
            contract_validation_written=contract_validation is not None,
        )
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
        "profile": build_paper_export_profile_payload(
            strict_profile=strict_profile,
            run_id=run_id,
            contract_version=contract_version,
            visual_family_support_threshold=export_settings["visual_family_support_threshold"],
            top_families_visual=export_settings["top_families_visual"],
            top_permissions=export_settings["top_permissions"],
            docs_paths=build_paper_docs_paths(docs_dir=paper_exports_root / "docs"),
        ),
        "artifact_paths": sorted(set([str(Path(path).resolve()) for path in exported_paths])),
    }
