# Filename: src/obsidiandroid/database/db_fetch_av_engine_raw_results.py
# Purpose  : Retrieve raw AV engine scan results for specified sample_id list from database
#
# Canonical implementation; ``database.db_fetch_av_engine_raw_results`` is an identity shim.

import pandas as pd
from . import db_engine
from obsidiandroid.cli.ui import display as du
from .verdict_semantics import VERDICT_METADATA_COLUMNS

# Columns to drop from the raw engine results
COLUMNS_TO_EXCLUDE = VERDICT_METADATA_COLUMNS - {"sample_id"}

# Core fetch function
def fetch_av_engine_results_for_samples(samples_df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    if "sample_id" not in samples_df.columns:
        du.print_error("[DB FETCH] Provided DataFrame lacks 'sample_id' column.")
        return pd.DataFrame()

    sample_ids = samples_df["sample_id"].dropna().unique().tolist()
    if not sample_ids:
        du.print_warning("[DB FETCH] No sample_ids found to query.")
        return pd.DataFrame()

    placeholders = ', '.join(['%s'] * len(sample_ids))
    query = (
        "SELECT * FROM virustotal_sample_vendor_engine_verdicts "
        f"WHERE sample_id IN ({placeholders}) "
        "ORDER BY sample_id ASC"
    )

    try:
        result_df = db_engine.execute_query(
            query=query,
            params=sample_ids,
            fetch=True,
            return_columns=True,
            as_dataframe=True
        )

        if result_df.empty:
            du.print_warning("[DB FETCH] No AV engine results returned.")
            return result_df

        deduped_df = _deduplicate_sample_rows(result_df, verbose=verbose)
        cleaned_df = deduped_df.drop(columns=[col for col in COLUMNS_TO_EXCLUDE if col in deduped_df.columns])
        if "sample_id" in cleaned_df.columns:
            cleaned_df = cleaned_df.sort_values("sample_id", kind="mergesort").reset_index(drop=True)

        return cleaned_df

    except Exception as e:
        du.print_error(f"[DB FETCH] Query failed: {e}")
        return pd.DataFrame()


def _deduplicate_sample_rows(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Ensure one deterministic verdict row per sample_id.

    If duplicate sample_id rows exist, prefer the newest record using
    updated/created timestamps and record_id as tie-breakers.
    """
    if df.empty or "sample_id" not in df.columns:
        return df

    duplicate_count = int(df["sample_id"].duplicated(keep=False).sum())
    if duplicate_count == 0:
        return df

    if verbose:
        du.print_warning(
            f"[DB FETCH] Detected {duplicate_count} duplicate verdict row(s). "
            "Applying deterministic deduplication by latest timestamp."
        )

    sort_fields = [col for col in ("updated_at", "record_created_at", "record_id") if col in df.columns]
    if sort_fields:
        ordered = df.sort_values(["sample_id", *sort_fields], ascending=[True, *([False] * len(sort_fields))])
        return ordered.drop_duplicates(subset=["sample_id"], keep="first").reset_index(drop=True)

    ordered = df.sort_values("sample_id", kind="mergesort")
    return ordered.drop_duplicates(subset=["sample_id"], keep="last").reset_index(drop=True)
