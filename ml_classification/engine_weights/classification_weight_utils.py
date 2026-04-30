# Filename: ml_classification/classification_weight_utils.py

import pandas as pd
import numpy as np

# === Validate DataFrame structure and ensure required columns exist === #
def validate_dataframe_columns(df: pd.DataFrame, required_cols: set, context: str = "DataFrame") -> bool:
    if df.empty:
        print(f"[ERROR] {context} is empty.")
        return False
    missing = required_cols - set(df.columns)
    if missing:
        print(f"[ERROR] {context} is missing required columns: {', '.join(sorted(missing))}")
        return False
    return True

# === Normalize numerical features to a [0, 1] scale using min-max scaling === #
def normalize_columns(df: pd.DataFrame, column_map: dict, round_decimals: int = 4) -> pd.DataFrame:
    for raw_col, norm_col in column_map.items():
        if raw_col in df.columns:
            max_val = df[raw_col].max()
            min_val = df[raw_col].min()
            if max_val > min_val:
                df[norm_col] = ((df[raw_col] - min_val) / (max_val - min_val)).round(round_decimals)
            else:
                df[norm_col] = 0.0
                print(f"[WARNING] Column '{raw_col}' has no variation. '{norm_col}' set to 0.")
        else:
            df[norm_col] = 0.0
            print(f"[WARNING] Column '{raw_col}' not found. '{norm_col}' set to 0.")
    return df

# === Z-score normalization for numeric features === #
def zscore_columns(df: pd.DataFrame, column_map: dict, round_decimals: int = 4) -> pd.DataFrame:
    for raw_col, z_col in column_map.items():
        if raw_col in df.columns:
            mean = df[raw_col].mean()
            std = df[raw_col].std()
            if std > 0:
                df[z_col] = ((df[raw_col] - mean) / std).round(round_decimals)
            else:
                df[z_col] = 0.0
                print(f"[WARNING] Column '{raw_col}' has zero variance. '{z_col}' set to 0.")
        else:
            df[z_col] = 0.0
            print(f"[WARNING] Column '{raw_col}' not found. '{z_col}' set to 0.")
    return df

# === Compute ML composite weight for AV engines === #
def calculate_ml_weight(
    df: pd.DataFrame,
    use_metadata: bool = False,
    round_decimals: int = 4,
    alpha: float = 0.4,
    beta: float = 0.3,
    gamma: float = 0.3,
    use_zscore: bool = False
) -> pd.DataFrame:
    if use_metadata:
        norm_cols = [
            "Coverage % (Norm)",
            "Label Diversity (Norm)",
            "Family Specificity (Norm)"
        ]
        if not set(norm_cols).issubset(df.columns):
            print("[ERROR] Missing normalized metadata columns for advanced ML scoring.")
            return df
        base = (
            alpha * df[norm_cols[0]] +
            beta * df[norm_cols[1]] +
            gamma * df[norm_cols[2]]
        )
    else:
        norm_cols = [
            "Detection Rate (Norm)",
            "Coverage % (Norm)",
            "Tier Score (Norm)"
        ]
        if not set(norm_cols).issubset(df.columns):
            print("[ERROR] Missing normalized base columns for fallback scoring.")
            return df
        base = (
            0.4 * df[norm_cols[0]] +
            0.4 * df[norm_cols[1]] +
            0.2 * df[norm_cols[2]]
        )

    if use_zscore:
        # blend with z-score metrics if present for robustness
        z_map = {
            norm_cols[0]: norm_cols[0].replace("(Norm)", "(Z)"),
            norm_cols[1]: norm_cols[1].replace("(Norm)", "(Z)"),
            norm_cols[2]: norm_cols[2].replace("(Norm)", "(Z)")
        }
        if set(z_map.values()).issubset(df.columns):
            z_component = (
                0.4 * df[z_map[norm_cols[0]]] +
                0.4 * df[z_map[norm_cols[1]]] +
                0.2 * df[z_map[norm_cols[2]]]
            )
            base = (base + z_component) / 2

    df["ML Weight Score"] = base.round(round_decimals)

    # Add binning for feature interpretability
    df["ML Weight Tier"] = pd.qcut(df["ML Weight Score"], q=4, labels=["Low", "Moderate", "High", "Top"], duplicates='drop')
    return df

# === Print min/max range for selected normalized features === #
def summarize_normalized_columns(df: pd.DataFrame, columns: list) -> None:
    print("\n[INFO] Normalized Feature Summary:")
    for col in columns:
        if col in df.columns:
            print(f"• {col:<30} → Min: {df[col].min():.4f} | Max: {df[col].max():.4f} | Mean: {df[col].mean():.4f}")
        else:
            print(f"• {col:<30} → [NOT FOUND]")
