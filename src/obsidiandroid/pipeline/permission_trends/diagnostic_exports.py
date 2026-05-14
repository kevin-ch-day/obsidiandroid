"""Diagnostics and traceability exports for permission-trends reporting."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import app_config

from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.pipeline.permission_trends.bundle_io import (
    export_df_diagnostics_with_latest,
    export_df_with_latest,
)


def export_selected_visual_family_registry(
    *,
    sample_core_df: pd.DataFrame,
    visual_families: list[str],
    run_id: str,
) -> str:
    """Export deterministic visual-family selection registry for paper traceability."""
    min_support = safe_int_config_value(
        getattr(app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 20),
        default=20,
    )
    max_count = safe_int_config_value(getattr(app_config, "MAX_FAMILY_VISUAL_COUNT", 12), default=12)
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
            dedup = (
                dedup.sort_values(
                    by=["sample_count", "family_canonical"],
                    ascending=[False, True],
                    kind="mergesort",
                )
                .reset_index(drop=True)
            )
            dedup["rank"] = dedup.index + 1
            dedup["selected_reason"] = f"support>={max(min_support, 1)};top_{max(max_count, 1)}_by_sample_count"
            registry_df = dedup[["rank", "family_canonical", "type_slug", "sample_count", "selected_reason"]].copy()

    out = export_df_diagnostics_with_latest(
        registry_df,
        run_id=str(run_id),
        file_stem="selected_families_visual",
    )
    setattr(app_config, "RUNTIME_SELECTED_FAMILIES_VISUAL_PATH", str(out))
    return str(out)


def export_jsd_support_shortfall_artifact(
    *,
    run_id: str,
    selected_count: int,
    required_count: int,
    min_support: int,
) -> str:
    """Export explicit JSD shortfall diagnostics when policy cannot be met."""
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
    return export_df_diagnostics_with_latest(
        payload,
        run_id=str(run_id),
        file_stem="jsd_family_support_shortfall",
    )


def export_jsd_pair_verification(
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
    diag_out = export_df_diagnostics_with_latest(
        compact,
        run_id=str(run_id),
        file_stem="family_jsd_pairs_verification",
    )
    bundle_path: str | None = None
    if isinstance(bundle_dir, Path):
        bundle_path = export_df_with_latest(compact, run_id=run_id, file_stem=file_stem, bundle_dir=bundle_dir)
    setattr(app_config, "RUNTIME_FAMILY_JSD_PAIR_VERIFICATION_PATH", str(diag_out))
    return str(bundle_path) if isinstance(bundle_path, str) and bundle_path else str(diag_out)


__all__ = [
    "export_jsd_pair_verification",
    "export_jsd_support_shortfall_artifact",
    "export_selected_visual_family_registry",
]

