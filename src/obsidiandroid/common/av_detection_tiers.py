"""Map AV coverage percentages to human-readable detection tier labels (shared constants)."""

from __future__ import annotations

import pandas as pd

# === Detection Tier Definitions ===
DETECTION_TIERS = [
    {"min": 100, "max": 100, "label": "All Detection (100%)"},
    {"min": 90, "max": 99, "label": "Very High Detection (90–99%)"},
    {"min": 70, "max": 89, "label": "High Detection (70–89%)"},
    {"min": 50, "max": 69, "label": "Moderate Detection (50–69%)"},
    {"min": 30, "max": 49, "label": "Low Detection (30–49%)"},
    {"min": 10, "max": 29, "label": "Very Low Detection (10–29%)"},
    {"min": 1, "max": 9, "label": "Minimal Detection (1–9%)"},
    {"min": 0, "max": 0, "label": "No Detection (0%)"},
]

TIER_LABELS = [tier["label"] for tier in DETECTION_TIERS]


def get_detection_tier(coverage_pct: float) -> str:
    """Map a detection coverage % (float) to a tier label (str)."""
    for tier in DETECTION_TIERS:
        if tier["min"] <= coverage_pct <= tier["max"]:
            return tier["label"]
    return "Uncategorized"


def assign_tiers_to_dataframe(
    df: pd.DataFrame,
    coverage_column: str = "Coverage %",
    new_column: str = "Detection Tier",
) -> pd.DataFrame:
    """Add a column with detection tier labels from coverage percentages."""
    df = df.copy()
    df[new_column] = df[coverage_column].apply(get_detection_tier)
    return df


def tier_distribution_summary(df: pd.DataFrame, tier_column: str = "Detection Tier") -> pd.Series:
    """Return frequency distribution (value counts) of detection tiers."""
    if tier_column not in df.columns:
        raise ValueError(f"Column '{tier_column}' not found in DataFrame.")
    return df[tier_column].value_counts().reindex(TIER_LABELS, fill_value=0)


def get_tier_classification_score(tier_label: str) -> int:
    """Numeric score for a tier label (ML ranking / weighting)."""
    tier_rank = {label: i for i, label in enumerate(reversed(TIER_LABELS), start=0)}
    return tier_rank.get(tier_label, -1)


def add_numeric_tier_score(
    df: pd.DataFrame,
    tier_column: str = "Detection Tier",
    score_column: str = "Tier Score",
) -> pd.DataFrame:
    """Add a numerical tier score column."""
    df = df.copy()
    df[score_column] = df[tier_column].apply(get_tier_classification_score)
    return df


__all__ = [
    "DETECTION_TIERS",
    "TIER_LABELS",
    "add_numeric_tier_score",
    "assign_tiers_to_dataframe",
    "get_detection_tier",
    "get_tier_classification_score",
    "tier_distribution_summary",
]
