# Filename: assign_detection_tiers.py
# Purpose : Assign detection performance tiers using ML weight score, reliability, and tier score

import pandas as pd
from utils import display_utils as du

EXPORT_TIER_DEBUG_PATH = "output\\detection_tier_assignment.xlsx"

DETECTION_TIER_LABELS = [
    "Exceptional Detection",
    "Strong Detection",
    "Moderate Detection",
    "Weak Detection",
    "Poor Detection"
]

DETECTION_TIER_WEIGHTS = {
    "ML Weight Score": 0.5,
    "Reliability": 0.3,
    "Tier Score (Norm)": 0.2
}

def _validate_input(df: pd.DataFrame) -> bool:
    required = list(DETECTION_TIER_WEIGHTS.keys())
    missing = [col for col in required if col not in df.columns]
    if missing:
        du.print_error(f"[TIERS] Missing required columns: {missing}")
        return False
    return True

def _compute_composite_score(df: pd.DataFrame) -> pd.Series:
    score = pd.Series(0.0, index=df.index)
    for col, weight in DETECTION_TIER_WEIGHTS.items():
        score += weight * df[col].fillna(0.0)
    return score

def _assign_ordered_tiers(score_series: pd.Series, labels: list) -> pd.Series:
    try:
        return pd.qcut(score_series, q=len(labels), labels=labels[::-1])
    except Exception:
        return pd.cut(score_series, bins=len(labels), labels=labels[::-1])

def _export_debug(df: pd.DataFrame):
    try:
        df[[
            "Engine", "ML Weight Score", "Reliability", "Tier Score",
            "Detection Rate", "Coverage %", "Tier Score (Norm)",
            "Composite Detection Score", "Detection Tier"
        ]].to_excel(EXPORT_TIER_DEBUG_PATH, index=False)
        du.print_info(f"[EXPORT] Detection tier debug matrix saved to: {EXPORT_TIER_DEBUG_PATH}")
    except Exception as e:
        du.print_warning(f"[EXPORT] Failed to export detection tier debug matrix: {e}")

def classify_detection_performance(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    if not _validate_input(df):
        df["Detection Tier"] = "Unassigned"
        return df

    try:
        du.print_debug("[TIERS] Generating composite detection performance score...")
        df["Composite Detection Score"] = _compute_composite_score(df)

        df["Detection Tier"] = _assign_ordered_tiers(
            df["Composite Detection Score"],
            DETECTION_TIER_LABELS
        )

        if verbose:
            du.print_distribution(df["Detection Tier"], label="Detection Tier Distribution")
            du.print_statistical_range("Composite Detection Score", df["Composite Detection Score"].tolist())
            _export_debug(df)

    except Exception as e:
        df["Detection Tier"] = "Unassigned"
        du.print_warning(f"[TIERS] Detection tier assignment failed: {e}")

    return df
