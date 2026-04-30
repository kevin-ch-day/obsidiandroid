# Filename: av_score_calculator.py
# Description: Score AV vendors using normalized metrics and reliability penalties

import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from utils import display_utils as du

# Normalize a series using hybrid z-score + MinMax approach
def hybrid_normalize(series: pd.Series) -> pd.Series:
    series = series.fillna(0)
    if series.empty or series.std() == 0:
        return pd.Series([0.0] * len(series), index=series.index)
    z_scores = (series - series.mean()) / (series.std() + 1e-6)
    scaled = MinMaxScaler().fit_transform(z_scores.values.reshape(-1, 1)).flatten()
    return pd.Series(scaled, index=series.index)

# Ensure all required columns exist in vendor summary data
def validate_vendor_data(rows: list[dict], required_cols: list[str]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for col in required_cols:
        if col not in df.columns:
            df[col] = 0.0
    df = df.fillna(0.0)
    df = df.astype({col: "float64" for col in required_cols if col in df.columns})
    return df

# Compute vendor-level diagnostic ratios
def compute_vendor_ratios(df: pd.DataFrame) -> pd.DataFrame:
    df["Disambig Ratio"] = df["Multiple Match Labels"] / df["Detection Diversity"].replace(0, 1)
    df["Noise Ratio"] = df["Unknown Parsed (%)"] / 100.0
    return df

# Apply MinMax-normalized z-scores to core metrics
def normalize_all_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        du.print_error("[ERROR] Cannot normalize metrics: DataFrame is empty.")
        return df

    norm_columns = {
        "Norm_Enrichment": "Enrichment Score",
        "Norm_Accuracy": "Family Match Accuracy (%)",
        "Norm_Diversity": "Detection Diversity",
        "Norm_Disambig": "Disambig Ratio",
        "Norm_Noise": "Noise Ratio"
    }

    for norm_col, source_col in norm_columns.items():
        if source_col in df.columns:
            df[norm_col] = hybrid_normalize(df[source_col])
        else:
            df[norm_col] = 0.0
            du.print_warning(
                f"[WARN] Source column '{source_col}' missing — defaulting {norm_col} to 0.0"
            )

    return df

# Compute final scoring components from normalized metrics
def compute_intelligence_and_penalty(df: pd.DataFrame) -> pd.DataFrame:
    df["Intelligence Score"] = (
        (df["Norm_Enrichment"] + 1e-5) *
        (df["Norm_Accuracy"] + 1e-5) *
        (df["Norm_Diversity"] + 1e-5)
    ) ** (1 / 3)

    df["Reliability Penalty"] = (
        0.6 * np.log1p(df["Norm_Noise"]) +
        0.4 * np.log1p(df["Norm_Disambig"])
    )

    return df

# Compute final score and assign vendor performance tier
def finalize_vendor_scores(df: pd.DataFrame) -> pd.DataFrame:
    df["Final ML Score"] = (
        df["Intelligence Score"] - 0.35 * df["Reliability Penalty"]
    ).clip(lower=0.0, upper=1.0)

    def tier(score: float) -> str:
        if score >= 0.75: return "High Precision"
        if score >= 0.50: return "Strong Signal"
        if score >= 0.25: return "Moderate"
        if score >  0.00: return "Low Precision"
        return "Too Generic"

    df["Vendor Category"] = df["Final ML Score"].apply(tier)

    df["ML Score StdDev"] = df[
        ["Norm_Enrichment", "Norm_Accuracy", "Norm_Diversity"]
    ].std(axis=1)

    return df.sort_values(by="Final ML Score", ascending=False).reset_index(drop=True)

# Full scoring pipeline: validates → computes → returns final vendor score DataFrame
def compute_vendor_scores(summary_rows: list[dict]) -> pd.DataFrame:
    if not summary_rows:
        du.print_error("[ERROR] No summary rows provided for vendor score computation.")
        return pd.DataFrame()

    required = [
        "Enrichment Score", "Family Match Accuracy (%)", "Detection Diversity",
        "Unknown Parsed (%)", "Multiple Match Labels"
    ]

    df = validate_vendor_data(summary_rows, required)

    if df.empty:
        du.print_error("[ERROR] Vendor summary DataFrame is empty after validation.")
        return df

    df = compute_vendor_ratios(df)
    df = normalize_all_metrics(df)
    df = compute_intelligence_and_penalty(df)
    df = finalize_vendor_scores(df)

    return df
