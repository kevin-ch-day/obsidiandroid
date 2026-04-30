# Filename: utils/sample_metadata_preprocessor.py
# Purpose  : Validate, sanitize, and prepare sample metadata DataFrames for ML alignment

import pandas as pd
from utils import display_utils as du

# Check if 'sample_id' is in the index (either as direct name or level)
def _is_sample_id_in_index(df: pd.DataFrame) -> bool:
    return df.index.name == 'sample_id' or 'sample_id' in df.index.names

# Ensure 'sample_id' is a column — resets index if needed
def _promote_sample_id_from_index(df: pd.DataFrame, label: str) -> pd.DataFrame:
    if 'sample_id' not in df.columns and _is_sample_id_in_index(df):
        du.print_warning(f"[{label}] 'sample_id' detected in index — resetting to column.")
        df = df.reset_index()

    if 'sample_id' not in df.columns:
        raise ValueError(f"[{label}] Missing required column: 'sample_id'")

    return df

# Check for duplicate sample_id values — drop or raise
def _resolve_sample_id_duplicates(df: pd.DataFrame, label: str, drop: bool) -> pd.DataFrame:
    duplicates = df['sample_id'].duplicated()
    if not duplicates.any():
        return df

    count = int(duplicates.sum())
    if drop:
        du.print_warning(f"[{label}] {count} duplicate sample_id(s) found — dropping duplicates.")
        return df[~duplicates]
    raise ValueError(f"[{label}] Found {count} duplicate sample_id(s) — fix required.")

# Set 'sample_id' as index if configured
def _enforce_sample_id_index(df: pd.DataFrame, label: str, set_index: bool) -> pd.DataFrame:
    if set_index:
        if df.index.name != 'sample_id':
            du.print_info(f"[{label}] Enforcing 'sample_id' as index.")
            df = df.set_index('sample_id', drop=False)
    return df

# Validate and normalize a sample metadata DataFrame
def prepare_sample_dataframe(
    df: pd.DataFrame,
    label: str = "Sample Metadata",
    enforce_index: bool = False,
    drop_duplicate_rows: bool = False
) -> pd.DataFrame:
    # Begin preprocessing log
    du.print_subheader(f"Preparing '{label}' DataFrame for Classification")

    # Promote sample_id from index if necessary
    df = _promote_sample_id_from_index(df, label)

    # Check and resolve duplicates
    df = _resolve_sample_id_duplicates(df, label, drop=drop_duplicate_rows)

    # Optionally enforce sample_id as index
    df = _enforce_sample_id_index(df, label, set_index=enforce_index)

    # Final confirmation of shape
    du.print_success(f"[{label}] Structure valid — {len(df)} rows × {len(df.columns)} columns.")
    return df


__all__ = ["prepare_sample_dataframe"]
