# Filename: assign_tier_scores.py
# Purpose : Assign meaningful performance tiers to AV engines using detection + coverage metrics

import pandas as pd
from utils import display_utils as du

# Tier labels and explanations
TIER_LABELS_VERBOSE = {
    1: "Exceptional",
    2: "Strong",
    3: "Moderate",
    4: "Weak",
    5: "Low Performing",
    6: "No Performance"
}

TIER_LABELS_NUMERIC = [1, 2, 3, 4, 5, 6]

DEFAULT_WEIGHTS = {
    "Coverage %": 0.6,
    "Detection Rate": 0.4
}

def assign_tier_scores(df: pd.DataFrame, verbose: bool = True, weights: dict = DEFAULT_WEIGHTS) -> pd.DataFrame:
    required_cols = set(weights.keys())
    if df.empty or not required_cols.issubset(df.columns):
        missing = sorted(required_cols - set(df.columns))
        du.print_error(f"[TIERS] Missing required columns: {missing}")
        df["Tier Score"] = 6
        df["Tier Label"] = TIER_LABELS_VERBOSE[6]
        return df

    try:
        # Step 1: Compute composite score
        df["Composite Tier Metric"] = sum(
            weight * df[col].clip(0, 100) for col, weight in weights.items()
        )
        if verbose:
            formula = " + ".join([f"{w:.1f}×{c}" for c, w in weights.items()])
            du.print_info(f"[TIERS] Composite metric calculated using: {formula}")

        # Step 2: Flag engines with essentially no detection or coverage
        df["Tier Score"] = None
        no_perf_mask = (df["Coverage %"] <= 0.01) & (df["Detection Rate"] <= 0.01)
        df.loc[no_perf_mask, "Tier Score"] = 6

        # Step 3: Assign quantile-based scores for valid performers
        tier_candidates = df.loc[~no_perf_mask, "Composite Tier Metric"]
        if tier_candidates.nunique() < 5:
            df.loc[~no_perf_mask, "Tier Score"] = 3
            du.print_warning("[TIERS] Not enough unique values to apply qcut. Fallback to Tier 3.")
        else:
            try:
                tier_bins = pd.qcut(tier_candidates, q=5, labels=[1, 2, 3, 4, 5])
                df.loc[~no_perf_mask, "Tier Score"] = tier_bins.astype(int)
            except Exception as e:
                df.loc[~no_perf_mask, "Tier Score"] = 3
                du.print_warning(f"[TIERS] qcut failed. Fallback to Tier 3. Reason: {e}")

        # Step 4: Map human-readable labels
        df["Tier Label"] = df["Tier Score"].map(TIER_LABELS_VERBOSE).fillna("Unclassified")

        # Step 5: Diagnostics
        if verbose:
            du.print_tier_distribution(df["Tier Score"], label="AV Engine Tier Distribution")
            du.print_statistical_range("Composite Tier Metric", df["Composite Tier Metric"].tolist())
            du.print_metric_summary({
                "Composite Score - Min": df["Composite Tier Metric"].min(),
                "Composite Score - Max": df["Composite Tier Metric"].max(),
                "Composite Score - Mean": df["Composite Tier Metric"].mean(),
                "Composite Score - Std": df["Composite Tier Metric"].std(),
                "Total Tier 6 Engines": int(no_perf_mask.sum()),
                "Tier Uniqueness": df["Tier Score"].nunique()
            }, title="Composite Score Diagnostic Summary")

    except Exception as e:
        df["Tier Score"] = 6
        df["Tier Label"] = TIER_LABELS_VERBOSE[6]
        du.print_warning(f"[TIERS] Tier computation failed — fallback applied. Reason: {e}")

    return df
