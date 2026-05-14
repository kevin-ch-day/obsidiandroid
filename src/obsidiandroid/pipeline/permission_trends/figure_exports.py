"""Matplotlib figure exports for permission-trends reporting.

These helpers are used by the pipeline stage to keep `stage_permission_trends_report`
focused on orchestration and data preparation.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import app_config

from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.pipeline.permission_trends.constants import (
    ARTIFACT_GROUP_FIGURES,
)
from obsidiandroid.pipeline.permission_trends.bundle_manifest import resolve_bundle_artifact_dir
from obsidiandroid.pipeline.permission_trends import reporting_support as _perm_trends_reporting
from obsidiandroid.pipeline.permission_trends.reporting_support import (
    compact_permission_label,
    handle_reporting_exception,
)
from obsidiandroid.pipeline.permission_trends.stats import build_sample_level_permission_metrics


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


def export_banker_trends_line_plot(
    *,
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
        max_lines = max(safe_int_config_value(getattr(app_config, "MAX_TIME_SERIES_LINES", 4), default=4), 1)
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
        figures_dir = resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_FIGURES)
        run_path = figures_dir / f"banker_permission_trends_over_time_{run_id}.png"
        latest_path = figures_dir / "banker_permission_trends_over_time.latest.png"
        write_run_scoped = _perm_trends_reporting.write_run_scoped_permission_artifacts()
        fig.savefig(latest_path, dpi=_report_figure_dpi(), bbox_inches="tight")
        if write_run_scoped:
            fig.savefig(run_path, dpi=_report_figure_dpi(), bbox_inches="tight")
        plt.close(fig)
        return str(run_path if write_run_scoped else latest_path)
    except Exception as exc:
        handle_reporting_exception("banker_trends_line_plot", exc, fail_in_paper=True)
        return None


def export_confusion_bar_plot(
    *,
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
    figures_dir = resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_FIGURES)
    latest_path = figures_dir / "confusion_within_vs_cross_type.latest.png"
    fig.savefig(latest_path, dpi=_report_figure_dpi())
    run_path: Path | None = None
    if _perm_trends_reporting.write_run_scoped_permission_artifacts():
        run_path = figures_dir / f"confusion_within_vs_cross_type_{run_id}.png"
        fig.savefig(run_path, dpi=_report_figure_dpi())
    plt.close(fig)
    return str(run_path or latest_path)


def export_prevalence_heatmap(
    *,
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
    compact_labels = [compact_permission_label(col) for col in pivot.columns]
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(compact_labels, rotation=90, fontsize=7)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=8)
    ax.set_title(title)
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    fig.tight_layout()
    figures_dir = resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_FIGURES)
    latest_path = figures_dir / f"{file_stem}.latest.png"
    fig.savefig(latest_path, dpi=_report_figure_dpi())
    run_path: Path | None = None
    if _perm_trends_reporting.write_run_scoped_permission_artifacts():
        run_path = figures_dir / f"{file_stem}_{run_id}.png"
        fig.savefig(run_path, dpi=_report_figure_dpi())
    plt.close(fig)
    return str(run_path or latest_path)


def export_jsd_heatmap(
    *,
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
    figures_dir = resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_FIGURES)
    latest_path = figures_dir / f"{file_stem}.latest.png"
    fig.savefig(latest_path, dpi=_report_figure_dpi())
    run_path: Path | None = None
    if _perm_trends_reporting.write_run_scoped_permission_artifacts():
        run_path = figures_dir / f"{file_stem}_{run_id}.png"
        fig.savefig(run_path, dpi=_report_figure_dpi())
    plt.close(fig)
    return str(run_path or latest_path)


def export_banker_enrichment_bar_chart(
    *,
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
    compact_labels = [compact_permission_label(value) for value in top["permission"].tolist()]
    ax.barh(compact_labels, top["odds_ratio"], color="#2a9d8f")
    ax.set_xlabel("Odds Ratio (banker vs non-banker)")
    ax.set_ylabel("Permission")
    ax.set_title("Top 15 enriched permissions for banker")
    fig.tight_layout()
    figures_dir = resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_FIGURES)
    latest_path = figures_dir / "banker_enrichment_top15.latest.png"
    fig.savefig(latest_path, dpi=_report_figure_dpi())
    run_path: Path | None = None
    if _perm_trends_reporting.write_run_scoped_permission_artifacts():
        run_path = figures_dir / f"banker_enrichment_top15_{run_id}.png"
        fig.savefig(run_path, dpi=_report_figure_dpi())
    plt.close(fig)
    return str(run_path or latest_path)


def export_generic_scatter(
    *,
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
    metrics = build_sample_level_permission_metrics(sample_core_df, permission_rows_df)
    min_vendor_count = safe_int_config_value(
        getattr(app_config, "CONSENSUS_MIN_VENDOR_COUNT", 5),
        default=5,
    )
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
    ax.scatter(
        non_generic["consensus_score_all_vendors"],
        non_generic["permission_entropy"],
        s=12,
        alpha=0.5,
        label="non-generic",
    )
    ax.scatter(
        generic["consensus_score_all_vendors"],
        generic["permission_entropy"],
        s=12,
        alpha=0.6,
        label="generic",
    )
    ax.set_xlabel("Consensus score (all vendors)")
    ax.set_ylabel("Permission entropy")
    ax.set_title("Consensus vs permission entropy")
    ax.legend(loc="best")
    fig.tight_layout()
    figures_dir = resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_FIGURES)
    latest_path = figures_dir / "generic_consensus_vs_entropy.latest.png"
    fig.savefig(latest_path, dpi=_report_figure_dpi())
    run_path: Path | None = None
    if _perm_trends_reporting.write_run_scoped_permission_artifacts():
        run_path = figures_dir / f"generic_consensus_vs_entropy_{run_id}.png"
        fig.savefig(run_path, dpi=_report_figure_dpi())
    plt.close(fig)
    return str(run_path or latest_path)


def export_family_permission_heatmap(
    *,
    family_profiles_df: pd.DataFrame,
    visual_families: list[str],
    run_id: str,
    bundle_dir: Path,
    file_stem: str = "family_permission_heatmap_top12",
) -> str | None:
    """Export pruned family-permission prevalence heatmap for paper readability."""
    if not isinstance(family_profiles_df, pd.DataFrame) or family_profiles_df.empty or not visual_families:
        return None
    max_perms = safe_int_config_value(
        getattr(app_config, "MAX_FAMILY_HEATMAP_PERMISSIONS", 25),
        default=25,
    )
    scope_df = family_profiles_df.copy()
    if "profile_scope" in scope_df.columns:
        scope_df = scope_df[scope_df["profile_scope"].astype(str) == "main"].copy()
    scope_df = scope_df[scope_df["family_canonical"].astype(str).isin(set(visual_families))].copy()
    if scope_df.empty:
        return None
    return export_prevalence_heatmap(
        prevalence_df=scope_df,
        row_field="family_canonical",
        value_field="prevalence",
        run_id=run_id,
        file_stem=file_stem,
        bundle_dir=bundle_dir,
        top_k=max(max_perms, 1),
        title=f"Family permission heatmap (top {max(max_perms, 1)})",
    )

