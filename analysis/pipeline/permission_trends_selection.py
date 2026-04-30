"""Selection and visual-scope helpers for permission trends reporting."""

from __future__ import annotations

from typing import Any

import pandas as pd

from config import app_config


def normalize_analysis_scope() -> str:
    """Normalize analysis scope configuration."""
    value = str(getattr(app_config, "ANALYSIS_SCOPE", "all")).strip().lower()
    if value in {"all", "type", "family", "banker"}:
        return value
    return "all"


def include_banker_case_study(analysis_scope: str) -> bool:
    """Return whether banker-specific case-study artifacts should be emitted."""
    scope = str(analysis_scope).strip().lower()
    if scope == "banker":
        return True
    return bool(getattr(app_config, "ENABLE_BANKER_CASE_STUDY_ARTIFACTS", False))


def normalize_figure_mode() -> str:
    """Normalize figure mode configuration."""
    value = str(getattr(app_config, "FIGURE_MODE", "analysis")).strip().lower()
    if value in {"analysis", "paper"}:
        return value
    return "analysis"


def filter_type_prevalence_for_visuals(type_prevalence_df: pd.DataFrame) -> pd.DataFrame:
    """Filter type prevalence rows for visual use."""
    if not isinstance(type_prevalence_df, pd.DataFrame) or type_prevalence_df.empty:
        return pd.DataFrame()
    out = type_prevalence_df.copy()
    if bool(getattr(app_config, "EXCLUDE_UNKNOWN_TYPE_IN_VISUALS", True)):
        out = out[out["type_slug"].astype(str).str.lower() != "unknown"].copy()
    return out


def select_permissions_for_type_heatmap(
    *,
    method: str,
    top_k: int,
    type_prevalence_df: pd.DataFrame,
    discriminability_df: pd.DataFrame,
    permission_rows_df: pd.DataFrame,
) -> list[str]:
    """Select deterministic permission columns for the type heatmap."""
    mode = str(method).strip().lower()
    size = max(int(top_k), 1)
    if mode == "discriminability":
        picked = select_discriminative_permissions(discriminability_df, top_k=size)
        if picked:
            return picked
    if mode == "dangerous":
        picked = select_dangerous_permissions_for_heatmap(
            permission_rows_df=permission_rows_df,
            type_prevalence_df=type_prevalence_df,
            top_k=size,
        )
        if picked:
            return picked
    support = (
        type_prevalence_df.groupby("permission")["prevalence"]
        .mean()
        .sort_values(ascending=False)
        .head(size)
        .index
        .astype(str)
        .tolist()
        if isinstance(type_prevalence_df, pd.DataFrame) and not type_prevalence_df.empty
        else []
    )
    return support


def select_discriminative_permissions(discriminability_df: pd.DataFrame, top_k: int) -> list[str]:
    """Select top permissions by discriminability ranking."""
    if not isinstance(discriminability_df, pd.DataFrame) or discriminability_df.empty:
        return []
    ordered = discriminability_df.sort_values(["cramers_v", "mutual_information"], ascending=[False, False])
    selected = ordered["permission"].astype(str).head(max(int(top_k), 1)).tolist()
    return [item for item in selected if item]


def select_dangerous_permissions_for_heatmap(
    permission_rows_df: pd.DataFrame,
    type_prevalence_df: pd.DataFrame,
    top_k: int,
) -> list[str]:
    """Select dangerous permissions ordered by prevalence support."""
    if not isinstance(permission_rows_df, pd.DataFrame) or permission_rows_df.empty:
        return []
    dangerous_rows = permission_rows_df.copy()
    dangerous_rows["permission_string"] = dangerous_rows.get("permission_string", "").astype(str)
    dangerous_rows["protection_level"] = dangerous_rows.get("protection_level", "").astype(str).str.upper()
    dangerous_only = dangerous_rows[dangerous_rows["protection_level"].str.contains("DANGEROUS", regex=False)]
    if dangerous_only.empty:
        return []
    dangerous_set = set(dangerous_only["permission_string"].dropna().astype(str).tolist())
    prevalence = type_prevalence_df.copy() if isinstance(type_prevalence_df, pd.DataFrame) else pd.DataFrame()
    if prevalence.empty or "permission" not in prevalence.columns:
        return sorted(list(dangerous_set))[: max(int(top_k), 1)]
    filtered = prevalence[prevalence["permission"].astype(str).isin(dangerous_set)].copy()
    if filtered.empty:
        return sorted(list(dangerous_set))[: max(int(top_k), 1)]
    ordered = (
        filtered.groupby("permission")["prevalence"]
        .mean()
        .sort_values(ascending=False)
        .head(max(int(top_k), 1))
        .index
        .astype(str)
        .tolist()
    )
    return ordered


def select_visual_families(sample_core_df: pd.DataFrame) -> list[str]:
    """Select families for family-level visuals using support threshold and cap."""
    if not isinstance(sample_core_df, pd.DataFrame) or sample_core_df.empty:
        return []
    min_support = int(getattr(app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 20))
    max_count = int(getattr(app_config, "MAX_FAMILY_VISUAL_COUNT", 12))
    family_df = sample_core_df.copy()
    family_df["family_canonical"] = family_df.get("family_canonical", "").astype(str).str.strip()
    family_df = family_df[family_df["family_canonical"] != ""]
    counts = (
        family_df.groupby("family_canonical", as_index=False)
        .size()
        .rename(columns={"size": "sample_count"})
    )
    counts = counts[counts["sample_count"] >= max(min_support, 1)]
    counts = counts.sort_values(
        by=["sample_count", "family_canonical"],
        ascending=[False, True],
        kind="mergesort",
    )
    return counts["family_canonical"].astype(str).head(max(max_count, 1)).tolist()


def filter_jsd_for_visual_families(jsd_df: pd.DataFrame, visual_families: list[str]) -> pd.DataFrame:
    """Filter the family JSD matrix to the selected visual families."""
    if not isinstance(jsd_df, pd.DataFrame) or jsd_df.empty or not visual_families:
        return pd.DataFrame()
    family_col = str(jsd_df.columns[1]) if len(jsd_df.columns) > 1 else ""
    if not family_col or "other" not in jsd_df.columns:
        return pd.DataFrame()
    allowed = set(str(item) for item in visual_families)
    return jsd_df[
        jsd_df[family_col].astype(str).isin(allowed) & jsd_df["other"].astype(str).isin(allowed)
    ].copy()

