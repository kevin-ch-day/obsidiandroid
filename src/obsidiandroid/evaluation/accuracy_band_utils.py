# Filename: obsidiandroid/evaluation/accuracy_band_utils.py
# Purpose  : Utility for tiered accuracy band evaluation and reporting in malware classification models

from typing import List, Tuple

# Accuracy tiers mapped to thresholds and human-readable descriptions
ACCURACY_BAND_TIERS: List[Tuple[str, float, str]] = [
    ("T0", 0.975, "Benchmark Optimal (>= 97.5%)"),
    ("T1", 0.950, "Elite Performance (95-97%)"),
    ("T2", 0.900, "Very Strong (90-94%)"),
    ("T3", 0.850, "Strong (85-89%)"),
    ("T4", 0.800, "Above Average (80-84%)"),
    ("T5", 0.750, "Solid Baseline (75-79%)"),
    ("T6", 0.700, "Usable but Inconsistent (70-74%)"),
    ("T7", 0.650, "Weak but Functional (65-69%)"),
    ("T8", 0.600, "Borderline Classifier (60-64%)"),
    ("T9", 0.500, "Poor Performance (50-59%)"),
    ("T10", 0.300, "Critically Weak (30-49%)"),
    ("T11", 0.100, "Near-Random Guessing (10-29%)"),
    ("T12", 0.000, "No Predictive Value (< 10%)"),
]


def evaluate_accuracy_band(score: float) -> str:
    """Return tier code and description for a score."""
    for tier_code, threshold, description in ACCURACY_BAND_TIERS:
        if score >= threshold:
            return f"{tier_code} - {description}"
    return "Unclassified"


def get_accuracy_tier_code(score: float) -> str:
    """Return only tier code for a score."""
    for tier_code, threshold, _ in ACCURACY_BAND_TIERS:
        if score >= threshold:
            return tier_code
    return "T?"


def get_accuracy_band_description(score: float) -> str:
    """Return only tier description for a score."""
    for _, threshold, description in ACCURACY_BAND_TIERS:
        if score >= threshold:
            return description
    return "Unclassified"


def list_accuracy_tier_codes() -> List[str]:
    """Return all tier codes."""
    return [tier for tier, _, _ in ACCURACY_BAND_TIERS]


def list_accuracy_bands() -> List[str]:
    """Return all tier labels formatted for display."""
    return [f"{tier} -> {description}" for tier, _, description in ACCURACY_BAND_TIERS]


def accuracy_band_table(as_dicts: bool = False):
    """Return accuracy bands as list[dict] or DataFrame."""
    import pandas as pd

    data = [
        {"Tier": tier, "Threshold": threshold, "Description": description}
        for tier, threshold, description in ACCURACY_BAND_TIERS
    ]
    return data if as_dicts else pd.DataFrame(data)
