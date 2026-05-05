# Filename: ml_classification/ml_utils/feature_label_alignment_helper.py
# Purpose : Wrapper to align feature and label DataFrames with diagnostics, index validation, and exportable debug support

from typing import Tuple, Optional, Set
import pandas as pd
import os
from obsidiandroid.cli.ui import display as du
from ml_classification.ml_utils import feature_alignment_utils

# -------------------------------------------------------------------
# Main alignment wrapper with index validation and diagnostics
# -------------------------------------------------------------------
def perform_feature_label_alignment(
    feature_df: pd.DataFrame,
    label_df: pd.DataFrame,
    export_debug: bool = False,
    output_dir: str = "output/diagnostics"
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    du.print_subheader("Align Feature and Label Samples by Sample ID")

    # Basic metadata preview
    _preview_input_metadata(feature_df, label_df)

    # Ensure correct indexing
    feature_df, label_df = _validate_sample_id_indexing(feature_df, label_df)

    # Check critical field
    if 'sample_id' not in label_df.columns:
        du.print_error("[ALIGNMENT] 'sample_id' column missing from label DataFrame.")
        return None, None

    # Compare IDs between feature and label sets
    _shared_ids, feature_only, label_only = _preview_alignment_overlap(feature_df, label_df)

    # Export mismatches if requested
    if export_debug:
        _export_alignment_diagnostics(feature_only, label_only, output_dir)

    # Attempt alignment
    aligned_feature_df, aligned_labels_df = feature_alignment_utils.align_feature_and_label_rows(
        feature_df, label_df, verbose=True
    )

    if aligned_feature_df is None or aligned_labels_df is None:
        du.print_error("[PIPELINE] Feature-label alignment failed.")
        return None, None

    count = len(aligned_feature_df)
    if count < 50:
        du.print_warning(f"[ALIGNMENT] Only {count} samples aligned — model training may be unreliable.")

    return aligned_feature_df, aligned_labels_df

# -------------------------------------------------------------------
# Preview index type and shape diagnostics
# -------------------------------------------------------------------
def _preview_input_metadata(
    feature_df: pd.DataFrame,
    label_df: pd.DataFrame
):
    du.print_debug(f"Feature Index: {feature_df.index.name} — {len(feature_df)} rows")
    du.print_debug(f"Label Index  : {label_df.index.name} — {len(label_df)} rows")
    feature_cols = list(feature_df.columns)
    label_cols = list(label_df.columns)
    feature_preview = feature_cols[:12]
    label_preview = label_cols[:12]
    du.print_debug(
        f"Feature Columns: {len(feature_cols)} total | preview: {feature_preview}"
    )
    du.print_debug(
        f"Label Columns  : {len(label_cols)} total | preview: {label_preview}"
    )

# -------------------------------------------------------------------
# Ensures 'sample_id' is the index for both DataFrames
# -------------------------------------------------------------------
def _validate_sample_id_indexing(
    feature_df: pd.DataFrame,
    label_df: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame]:

    if feature_df.index.name != 'sample_id':
        if 'sample_id' in feature_df.columns:
            du.print_warning("[INDEX FIX] Setting feature_df index to 'sample_id'.")
            feature_df = feature_df.set_index('sample_id', drop=False)
        else:
            du.print_error("[INDEX ERROR] 'sample_id' not found in feature_df columns.")
    
    if label_df.index.name != 'sample_id':
        if 'sample_id' in label_df.columns:
            du.print_warning("[INDEX FIX] Setting label_df index to 'sample_id'.")
            label_df = label_df.set_index('sample_id', drop=False)
        else:
            du.print_error("[INDEX ERROR] 'sample_id' not found in label_df columns.")

    return feature_df, label_df

# -------------------------------------------------------------------
# Reports overlap and mismatches between sample ID sets
# -------------------------------------------------------------------
def _preview_alignment_overlap(
    feature_df: pd.DataFrame,
    label_df: pd.DataFrame
) -> Tuple[Set[str], Set[str], Set[str]]:

    feature_ids = set(feature_df.index)
    label_ids = set(label_df['sample_id'])

    shared_ids = feature_ids & label_ids
    feature_only = feature_ids - label_ids
    label_only = label_ids - feature_ids

    du.print_info(f"[ALIGNMENT] Shared sample_ids: {len(shared_ids)}")
    du.print_info(f"[ALIGNMENT] Features not in labels: {len(feature_only)}")
    du.print_info(f"[ALIGNMENT] Labels not in features: {len(label_only)}")

    if feature_only:
        preview = ', '.join(map(str, sorted(list(feature_only))[:5]))
        du.print_debug(f"[DROPPED FEATURES] Example IDs: {preview}")
    if label_only:
        preview = ', '.join(map(str, sorted(list(label_only))[:5]))
        du.print_debug(f"[DROPPED LABELS] Example IDs: {preview}")

    return shared_ids, feature_only, label_only

# -------------------------------------------------------------------
# Writes unmatched sample IDs to diagnostic files
# -------------------------------------------------------------------
def _export_alignment_diagnostics(
    feature_only: Set[str],
    label_only: Set[str],
    output_dir: str
):
    os.makedirs(output_dir, exist_ok=True)

    feature_path = os.path.join(output_dir, "unmatched_feature_ids.csv")
    label_path = os.path.join(output_dir, "unmatched_label_ids.csv")

    pd.Series(sorted(feature_only)).to_csv(feature_path, index=False, header=["sample_id"])
    pd.Series(sorted(label_only)).to_csv(label_path, index=False, header=["sample_id"])

    du.print_info(f"[EXPORT] Unmatched feature IDs saved to: {feature_path}")
    du.print_info(f"[EXPORT] Unmatched label IDs  saved to: {label_path}")
