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
    text = "\n".join(lines) + "\n"
    return export_markdown_with_latest(text, run_id, "run_summary_onepager", bundle_dir)


__all__ = [
    "build_permission_trends_layout_check",
    "export_alias_map_csv",
    "export_paper_figures_index",
    "export_run_summary_onepager",
    "export_safe_claims_report",
]
