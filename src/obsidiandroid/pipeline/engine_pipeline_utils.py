# Filename: obsidiandroid/pipeline/engine_pipeline_utils.py
# Purpose : Utility functions for AV engine pipeline input validation and metadata fetching
#
# Canonical AV-engine pipeline utilities.

import pandas as pd
from obsidiandroid.cli.ui import display as du
from obsidiandroid.database import db_av_engine_detection_totals


def validate_sample_input(samples_df: pd.DataFrame) -> bool:
    """
    Validates the sample DataFrame required by the AV analysis pipeline.

    Returns True if the DataFrame is non-empty and includes 'sample_id',
    otherwise logs an error and returns False.
    """
    if samples_df is None or samples_df.empty:
        du.print_error("[ABORT] Input sample DataFrame is empty.")
        return False

    if "sample_id" not in samples_df.columns:
        du.print_error("[ABORT] Missing required column: 'sample_id'.")
        return False

    return True


def fetch_engine_metadata(verbose: bool = True) -> pd.DataFrame:
    """
    Fetches AV engine metadata from the database, validating required fields.

    Returns:
        pd.DataFrame: Validated metadata or an empty DataFrame if failed.
    """
    try:
        engine_df = db_av_engine_detection_totals.get_engine_detection_totals(as_dataframe=True)

        if not isinstance(engine_df, pd.DataFrame):
            raise TypeError("[META] Returned object is not a DataFrame.")
        if engine_df.empty:
            raise ValueError("[META] Retrieved engine metadata is empty.")

        required_columns = {
            "engine_name", "detection_strategy", "is_trusted_vendor", "is_engine_active"
        }
        missing_columns = required_columns - set(engine_df.columns)
        if missing_columns:
            raise KeyError(f"[META] Missing required metadata fields: {sorted(missing_columns)}")

        if verbose:
            du.print_debug(f"[META] Loaded engine metadata with {engine_df.shape[0]} rows.")

        return engine_df

    except Exception as e:
        du.print_warning(f"[META] Failed to fetch or validate engine metadata: {e}")
        return pd.DataFrame()
