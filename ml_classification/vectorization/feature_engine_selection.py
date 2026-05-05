# Filename: ml_classification/vectorization/feature_engine_selection.py
# Purpose  : Select top AV engines by score and filter vendor categories for ML feature generation

import pandas as pd
from typing import List, Optional
from config import app_config
from obsidiandroid.cli.ui import display as du


def get_top_engines_by_score(
    weights_df: pd.DataFrame,
    top_k: int = 10,
    score_preference: Optional[str] = None,
    exclude_categories: Optional[List[str]] = None,
    min_score: Optional[float] = None,
    verbose: bool = True,
    enforce_included_in_model: bool = True,
) -> List[str]:
    """
    Select top AV engines based on scoring criteria, excluding specified categories.

    Args:
        weights_df (pd.DataFrame): Vendor engine weights table with score columns.
        top_k (int): Number of top vendors to select.
        score_preference (str, optional): Preferred score column name.
        exclude_categories (List[str], optional): Categories of vendors to exclude.
        min_score (float, optional): Minimum score threshold; rows below are removed.
        verbose (bool): Print debug info.
        enforce_included_in_model (bool): Filter to governance-included vendors when available.

    Returns:
        List[str]: Sorted list of top vendor names by score.
    """
    fallback_scores = ["effective_weight", "Final ML Score", "Composite Score", "Score", "Normalized Score"]
    score_field = score_preference or next((s for s in fallback_scores if s in weights_df.columns), None)

    if not score_field:
        raise KeyError(f"[ERROR] No usable score column found. Tried: {', '.join(fallback_scores)}")

    if "Vendor" in weights_df.columns:
        weights_df = weights_df.set_index("Vendor")

    if enforce_included_in_model and "included_in_model" in weights_df.columns:
        before = len(weights_df)
        weights_df = weights_df[weights_df["included_in_model"] == 1]
        if verbose and before != len(weights_df):
            du.print_info(f"[FILTER] Excluded {before - len(weights_df)} vendors failing parser gates.")

    enforce_trusted = bool(getattr(app_config, "FEATURE_ENFORCE_TRUSTED_VENDOR", False))
    if enforce_trusted:
        if "trusted_vendor_flag" in weights_df.columns:
            before = len(weights_df)
            weights_df = weights_df[pd.to_numeric(weights_df["trusted_vendor_flag"], errors="coerce").fillna(0).astype(int) == 1]
            if verbose and before != len(weights_df):
                du.print_info(
                    f"[FILTER] Excluded {before - len(weights_df)} non-trusted vendors "
                    "(FEATURE_ENFORCE_TRUSTED_VENDOR=True)."
                )
        elif verbose:
            du.print_warning(
                "[FILTER] FEATURE_ENFORCE_TRUSTED_VENDOR=True but 'trusted_vendor_flag' "
                "is unavailable; skipping trusted-only filter."
            )

    if exclude_categories and "Vendor Category" in weights_df.columns:
        initial_count = len(weights_df)
        weights_df = weights_df[~weights_df["Vendor Category"].isin(exclude_categories)]
        filtered_count = len(weights_df)
        if verbose:
            du.print_info(
                f"[FILTER] Excluded {initial_count - filtered_count} vendors "
                f"from categories: {exclude_categories}"
            )

    if min_score is not None:
        initial_count = len(weights_df)
        scores = pd.to_numeric(weights_df[score_field], errors="coerce").fillna(float("-inf"))
        weights_df = weights_df.loc[scores >= float(min_score)]
        filtered_count = len(weights_df)
        if verbose:
            du.print_info(
                f"[FILTER] Excluded {initial_count - filtered_count} vendors below "
                f"score threshold {float(min_score):.4f} on '{score_field}'"
            )

    if weights_df.empty:
        if verbose:
            du.print_warning("[SELECT] No vendors remain after filtering.")
        return []

    top_vendors = (
        weights_df.sort_values(by=score_field, ascending=False)
        .head(top_k)
        .index.tolist()
    )

    if top_vendors:
        selected_scores = pd.to_numeric(
            weights_df.loc[top_vendors, score_field], errors="coerce"
        ).fillna(float("-inf"))
        n_non_positive = int((selected_scores <= 0).sum())
        if n_non_positive > 0 and verbose:
            du.print_warning(
                f"[SELECT] {n_non_positive}/{len(top_vendors)} selected vendor(s) have "
                f"non-positive '{score_field}' values."
            )

    if verbose:
        du.print_info(f"[SELECT] Top {len(top_vendors)} vendors by '{score_field}': {top_vendors}")

    return top_vendors
