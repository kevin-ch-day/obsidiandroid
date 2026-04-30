# Filename: compute_reliability_score.py
# Purpose : Compute and diagnose reliability scores for AV engines using normalized metrics

import pandas as pd
import numpy as np
from utils import display_utils as du

REQUIRED_COLUMNS = [
    "Detection Rate (Norm)",
    "Coverage % (Norm)",
    "Tier Score (Norm)"
]

RELIABILITY_WEIGHTS = {
    "detection": 0.5,
    "coverage": 0.3,
    "tier_inverse": 0.2,
}

RELIABILITY_Z_WEIGHTS = {
    "detection": 0.5,
    "coverage": 0.3,
    "tier_inverse": 0.2,
}

RELIABILITY_BANDS = {
    "Exceptional": (0.875, 1.01),
    "Very High":   (0.775, 0.875),
    "High":        (0.675, 0.775),
    "Above Avg":   (0.575, 0.675),
    "Moderate":    (0.475, 0.575),
    "Below Avg":   (0.375, 0.475),
    "Low":         (0.200, 0.375),
    "None":        (0.000, 0.200)
}

def _compute_inverse_tier(df: pd.DataFrame) -> pd.Series:
    return 1.0 - df["Tier Score (Norm)"].clip(0, 1)

def _compute_weighted_reliability(df: pd.DataFrame) -> pd.Series:
    return (
        RELIABILITY_WEIGHTS["detection"] * df["Detection Rate (Norm)"] +
        RELIABILITY_WEIGHTS["coverage"] * df["Coverage % (Norm)"] +
        RELIABILITY_WEIGHTS["tier_inverse"] * _compute_inverse_tier(df)
    ).round(4)

def _compute_weighted_reliability_z(df: pd.DataFrame) -> pd.Series:
    if {"Detection Rate (Z)", "Coverage % (Z)", "Tier Score (Z)"}.issubset(df.columns):
        return (
            RELIABILITY_Z_WEIGHTS["detection"] * df["Detection Rate (Z)"] +
            RELIABILITY_Z_WEIGHTS["coverage"] * df["Coverage % (Z)"] +
            RELIABILITY_Z_WEIGHTS["tier_inverse"] * (1 - df["Tier Score (Z)"])
        ).round(4)
    return pd.Series(0.0, index=df.index)

def _assign_band(score: float) -> str:
    for label, (low, high) in RELIABILITY_BANDS.items():
        if low <= score < high:
            return label
    return "Unknown"

def _apply_band_labels(df: pd.DataFrame) -> pd.Series:
    return df["Reliability"].apply(_assign_band)

def _validate_input(df: pd.DataFrame) -> list:
    return [col for col in REQUIRED_COLUMNS if col not in df.columns]

def _summarize_reliability(df: pd.DataFrame):
    du.print_metric_summary({
        "Reliability Min": df["Reliability"].min(),
        "Reliability Max": df["Reliability"].max(),
        "Reliability Mean": df["Reliability"].mean(),
        "Reliability Std Dev": df["Reliability"].std(),
        "Reliability Bands": df["Reliability Band"].value_counts().to_dict()
    }, title="Reliability Score Summary")
    du.print_statistical_range("Reliability Score", df["Reliability"].tolist())
    if "Reliability_z" in df.columns:
        du.print_statistical_range("Reliability_z", df["Reliability_z"].tolist())

def compute_reliability(df: pd.DataFrame, verbose: bool = False) -> pd.DataFrame:
    missing = _validate_input(df)
    if missing:
        du.print_warning(f"[RELIABILITY] Missing required fields: {missing}")
        df["Reliability"] = 0.0
        df["Reliability Band"] = "Unknown"
        return df

    df["Reliability"] = _compute_weighted_reliability(df)
    df["Reliability_z"] = _compute_weighted_reliability_z(df)
    if (df["Reliability_z"] != 0).any():
        df["Reliability"] = (df["Reliability"] + df["Reliability_z"].apply(lambda x: 1/(1+np.exp(-x)))) / 2
    df["Reliability Band"] = _apply_band_labels(df)

    if verbose:
        du.print_info("[RELIABILITY] Composite reliability score computed using weighted metrics.")
        _summarize_reliability(df)

    return df
