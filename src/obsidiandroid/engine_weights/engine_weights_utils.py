# Filename: engine_weights_utils.py
# Purpose : Utility layer for AV engine weight score processing and feature enrichment

import pandas as pd
from . import classification_weight_utils as cwutils
from obsidiandroid.cli.ui import display as du

# Required normalized metric columns
NORMALIZATION_MAP = {
    "Detection Rate": "Detection Rate (Norm)",
    "Coverage %": "Coverage % (Norm)",
    "Tier Score": "Tier Score (Norm)"
}

# Metadata normalization map
METADATA_NORMALIZATION = {
    "Label Diversity": "Label Diversity (Norm)",
    "Named Family Hits": "Family Specificity (Norm)"
}

def validate_input_columns(df: pd.DataFrame, required: set, context: str = "Input Data") -> bool:
    missing = required - set(df.columns)
    if missing:
        du.print_error(f"[VALIDATION] Missing required columns in {context}: {sorted(missing)}")
        return False
    return True

ZSCORE_MAP = {
    "Detection Rate": "Detection Rate (Z)",
    "Coverage %": "Coverage % (Z)",
    "Tier Score": "Tier Score (Z)"
}

def normalize_base_indicators(df: pd.DataFrame, verbose: bool = False, use_zscore: bool = True) -> pd.DataFrame:
    try:
        df = cwutils.normalize_columns(df, NORMALIZATION_MAP)
        if use_zscore:
            df = cwutils.zscore_columns(df, ZSCORE_MAP)
        if verbose:
            du.print_debug(
                f"[NORMALIZE] Applied normalization to: {list(NORMALIZATION_MAP.keys())}" +
                (" with z-score" if use_zscore else "")
            )
        return df
    except Exception as e:
        du.print_warning(f"[NORMALIZE] Failed to normalize metrics: {e}")
        return df

def add_metadata_fields(df: pd.DataFrame, label_metadata: dict, verbose: bool = False) -> pd.DataFrame:
    if not label_metadata:
        du.print_warning("[LABELS] No label metadata provided. Skipping enrichment.")
        return df

    try:
        df["Label Diversity"] = df["Engine"].map(lambda e: label_metadata.get(e, {}).get("unique_labels", 0))
        df["Named Family Hits"] = df["Engine"].map(lambda e: label_metadata.get(e, {}).get("named_family_count", 0))

        df = cwutils.normalize_columns(df, METADATA_NORMALIZATION)

        if verbose:
            du.print_debug("[LABELS] Enriched DataFrame with normalized metadata features.")

    except Exception as e:
        du.print_warning(f"[LABELS] Metadata enrichment failed: {e}")

    return df
