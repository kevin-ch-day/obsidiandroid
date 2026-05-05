# Filename: obsidiandroid/evaluation/av_results_fetcher.py
# Description: Fetches raw AV engine results from the database for given samples with diagnostic logging.

import pandas as pd

from obsidiandroid.cli.ui import display as du
from obsidiandroid.database import db_fetch_av_engine_raw_results


def fetch_av_results(samples_df: pd.DataFrame, verbose: bool = False) -> pd.DataFrame:
    """
    Retrieve AV engine detection results from the database using sample identifiers.

    Args:
        samples_df (pd.DataFrame): Input sample metadata with at least a 'sample_id' column.
        verbose (bool): Enable verbose logging and diagnostics.

    Returns:
        pd.DataFrame: AV result matrix (rows = samples, columns = AV engines).
                      Empty DataFrame if no results are returned.
    """
    du.print_section("AV Results Fetcher")

    if "sample_id" not in samples_df.columns:
        du.print_error("[FETCH] Input DataFrame missing required 'sample_id' column.")
        return pd.DataFrame()

    # Query database using provided sample IDs
    av_df = db_fetch_av_engine_raw_results.fetch_av_engine_results_for_samples(samples_df, verbose)

    # Output diagnostics
    if av_df.empty:
        du.print_error("[FETCH] No AV engine results retrieved from the database.")
    elif verbose:
        du.print_info(f"[FETCH] Retrieved AV result matrix → shape: {av_df.shape}")
        du.print_debug(f"[FETCH] Sample AV result preview (columns): {list(av_df.columns)[:10]}")

    return av_df
