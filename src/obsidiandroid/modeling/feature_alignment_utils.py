"""Align ML feature and label DataFrames by sample ID with diagnostics."""

from typing import Tuple, Optional
import pandas as pd
from obsidiandroid.cli.ui import display as du

# -------------------------------------------------------------------
# Main alignment entry point
# -------------------------------------------------------------------
def align_feature_and_label_rows(
    features_df: pd.DataFrame,
    labels_df: pd.DataFrame,
    verbose: bool = True
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    # Validate input structure
    if not _validate_inputs(features_df, labels_df):
        return None, None

    # Auto-fix index misalignment if sample_id exists as a column
    features_df = _ensure_sample_id_index(features_df, role="Features", verbose=verbose)
    labels_df = _ensure_sample_id_index(labels_df, role="Labels", verbose=verbose)

    # Diagnostics before alignment
    if verbose:
        _print_dataframe_info(features_df, labels_df)
        _preview_sample_ids(features_df, labels_df)

    # Detect shared sample IDs
    common_ids = features_df.index.intersection(labels_df.index)
    if common_ids.empty:
        du.print_error("[ALIGNMENT ERROR] No matching sample IDs found.")
        return None, None

    # Align both DataFrames by sample_id
    aligned_features = features_df.loc[common_ids].copy()
    aligned_labels = labels_df.loc[common_ids].copy()

    # Report dropped sample records
    _report_dropped_samples(features_df, labels_df, common_ids, verbose)

    du.print_success(f"[ALIGNMENT] Successfully aligned {len(common_ids)} sample(s).")
    return aligned_features, aligned_labels

# -------------------------------------------------------------------
# Validates whether the input DataFrames are usable
# -------------------------------------------------------------------
def _validate_inputs(
    features_df: pd.DataFrame,
    labels_df: pd.DataFrame
) -> bool:
    if not isinstance(features_df, pd.DataFrame) or features_df.empty:
        du.print_error("[INPUT] Feature matrix is missing or empty.")
        return False
    if not isinstance(labels_df, pd.DataFrame) or labels_df.empty:
        du.print_error("[INPUT] Label DataFrame is missing or empty.")
        return False
    return True

# -------------------------------------------------------------------
# Ensure 'sample_id' is used as index
# -------------------------------------------------------------------
def _ensure_sample_id_index(
    df: pd.DataFrame,
    role: str,
    verbose: bool
) -> pd.DataFrame:
    if df.index.name != 'sample_id':
        if 'sample_id' in df.columns:
            if verbose:
                du.print_warning(f"[{role}] Index is not 'sample_id'. Auto-setting index using 'sample_id' column.")
            df = df.set_index("sample_id", drop=False)
        else:
            du.print_error(f"[{role}] Missing 'sample_id' index and column.")
    return df

# -------------------------------------------------------------------
# Print shape, index, and type info
# -------------------------------------------------------------------
def _print_dataframe_info(
    features_df: pd.DataFrame,
    labels_df: pd.DataFrame
):
    du.print_info(
        "[ALIGNMENT] Input: {rows:,} rows | {features:,} feature columns | {labels:,} label fields".format(
            rows=len(features_df),
            features=features_df.shape[1],
            labels=labels_df.shape[1],
        )
    )

    if features_df.index.name != labels_df.index.name:
        du.print_warning(f"[INDEX WARNING] Index name mismatch → Features='{features_df.index.name}', Labels='{labels_df.index.name}'")

# -------------------------------------------------------------------
# Preview example sample IDs
# -------------------------------------------------------------------
def _preview_sample_ids(
    features_df: pd.DataFrame,
    labels_df: pd.DataFrame
):
    try:
        du.print_debug(f"Feature Index Sample IDs (first 3): {features_df.index.tolist()[:3]}")
        du.print_debug(f"Label Index Sample IDs (first 3): {labels_df.index.tolist()[:3]}")
    except Exception as e:
        du.print_debug(f"Failed to preview index values: {e}")

# -------------------------------------------------------------------
# Report which sample IDs were dropped
# -------------------------------------------------------------------
def _report_dropped_samples(
    features_df: pd.DataFrame,
    labels_df: pd.DataFrame,
    common_ids: pd.Index,
    verbose: bool = True
):
    dropped_features = features_df.index.difference(common_ids)
    dropped_labels = labels_df.index.difference(common_ids)

    if dropped_features.any():
        du.print_warning(f"[ALIGNMENT] Dropped {len(dropped_features)} unmatched feature sample(s).")
        if verbose:
            preview = sorted(dropped_features.tolist())[:5]
            du.print_debug(f"[DROPPED FEATURES] Sample IDs: {preview}...")

    if dropped_labels.any():
        du.print_warning(f"[ALIGNMENT] Dropped {len(dropped_labels)} unmatched label sample(s).")
        if verbose:
            preview = sorted(dropped_labels.tolist())[:5]
            du.print_debug(f"[DROPPED LABELS] Sample IDs: {preview}...")
