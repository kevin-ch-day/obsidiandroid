# Filename: prepare_engine_metrics_for_ml.py
# Purpose : Prepare and normalize AV engine scores for ML readiness in ObsidianDroid

import pandas as pd
from utils import display_utils as du

REQUIRED_METRIC_COLUMNS = {"Engine", "Coverage %", "Detection Rate", "Tier Score"}
EXPORT_DEBUG_INPUT_PATH = "output\\debug_engine_df.xlsx"

def prepare_engine_metrics_for_ml(engine_df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    if engine_df.empty:
        du.print_error("[ENGINE PREP] Input engine DataFrame is empty.")
        return pd.DataFrame()

    # Export raw input for debugging
    try:
        engine_df.to_excel(EXPORT_DEBUG_INPUT_PATH, index=False)
        du.print_info(f"[EXPORT] Raw engine DataFrame saved to: {EXPORT_DEBUG_INPUT_PATH}")
    except Exception as e:
        du.print_warning(f"[EXPORT] Failed to export raw engine DataFrame: {e}")

    if verbose:
        du.print_debug(f"[ENGINE PREP] Raw input shape: {engine_df.shape}")

    # Normalize + transform
    df = _standardize_column_headers(engine_df, verbose)
    df = _inject_missing_fields(df, verbose)

    # Inline required field validation
    missing = REQUIRED_METRIC_COLUMNS - set(df.columns)
    if missing:
        du.print_error(f"[ENGINE PREP] Missing required columns: {sorted(missing)}")
        return pd.DataFrame()

    df = _convert_numeric_metrics(df, verbose)
    df = _normalize_and_flag_fields(df, verbose)
    df = _attach_derived_flags(df, verbose)

    if verbose:
        _print_engine_feature_summary(df)

    return df[[
        "Engine", "Coverage %", "Detection Rate", "Tier Score",
        "Coverage % (Norm)", "Tier Score (Norm)",
        "high_precision_flag", "low_coverage_flag", "zero_variance_flag"
    ]]

# -----------------------------------------------------------------------------
# Support Functions
# -----------------------------------------------------------------------------

def _standardize_column_headers(df: pd.DataFrame, verbose: bool) -> pd.DataFrame:
    aliases = {
        "Engine Name": "Engine", "engine_name": "Engine",
        "Detection %": "Detection Rate", "Detection Rate": "Detection Rate",
        "Detection Tier": "Tier Score", "Tier Score": "Tier Score",
        "Coverage %": "Coverage %"
    }
    renamed = df.rename(columns={col: aliases.get(col, col) for col in df.columns})
    if verbose:
        du.print_debug(f"[ENGINE PREP] Standardized columns: {list(renamed.columns)}")
    return renamed

def _inject_missing_fields(df: pd.DataFrame, verbose: bool) -> pd.DataFrame:
    if "Detection Rate" not in df.columns and {"Malicious Flags", "Samples Scanned"}.issubset(df.columns):
        df["Detection Rate"] = (df["Malicious Flags"] / df["Samples Scanned"] * 100).round(2)
        if verbose:
            du.print_info("[ENGINE PREP] Inferred 'Detection Rate' from Malicious Flags / Samples Scanned.")
    return df

def _convert_numeric_metrics(df: pd.DataFrame, verbose: bool) -> pd.DataFrame:
    for col in REQUIRED_METRIC_COLUMNS - {"Engine"}:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
        if verbose:
            du.print_debug(f"[ENGINE PREP] Converted column '{col}' to numeric.")
    return df

def _normalize_and_flag_fields(df: pd.DataFrame, verbose: bool) -> pd.DataFrame:
    variance_flags = []
    for col in ["Coverage %", "Tier Score"]:
        norm_col = f"{col} (Norm)"
        if df[col].nunique() <= 1:
            df[norm_col] = 0.0
            variance_flags.append(1)
            if verbose:
                du.print_warning(f"[ENGINE PREP] '{col}' has no variance — Normalized to 0.")
        else:
            col_min, col_max = df[col].min(), df[col].max()
            df[norm_col] = ((df[col] - col_min) / (col_max - col_min)).round(4)
            variance_flags.append(0)
    df["zero_variance_flag"] = int(any(variance_flags))
    return df

def _attach_derived_flags(df: pd.DataFrame, verbose: bool) -> pd.DataFrame:
    df["high_precision_flag"] = (df["Detection Rate"] >= 90.0).astype(int)
    df["low_coverage_flag"] = (df["Coverage %"] < 50.0).astype(int)
    if verbose:
        du.print_debug("[ENGINE PREP] Flags added: high_precision_flag, low_coverage_flag")
    return df

def _print_engine_feature_summary(df: pd.DataFrame):
    du.print_metric_summary({
        "Avg Detection Rate": df["Detection Rate"].mean(),
        "Avg Coverage %": df["Coverage %"].mean(),
        "Unique Tier Scores": df["Tier Score"].nunique()
    }, title="Engine Metric Summary")

    du.print_statistical_range("Detection Rate (%)", df["Detection Rate"].tolist())
    du.print_tier_distribution(df["Tier Score"], label="Tier Score Distribution")
