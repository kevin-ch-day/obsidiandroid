# Filename: enrich_malicious_scores.py
# Purpose  : Enrich AV detection matrix with scoring metadata and derived features

import pandas as pd
from database import db_sample_malicious_scoring
from . import enrich_score_features

# --- Validation ---
def is_valid_av_matrix(df: pd.DataFrame) -> bool:
    """Check if the AV matrix is valid for enrichment."""
    return isinstance(df, pd.DataFrame) and not df.empty and "sample_id" in df.columns


# --- Load scoring data ---
def fetch_malicious_score_table() -> pd.DataFrame:
    """Fetches malicious scoring data from the database."""
    try:
        result = db_sample_malicious_scoring.get_sample_malicious_score()
        if not isinstance(result, (list, tuple)) or len(result) != 2:
            return pd.DataFrame()
        rows, cols = result
        if not rows or not cols:
            return pd.DataFrame()
        return pd.DataFrame(rows, columns=cols)
    except Exception:
        return pd.DataFrame()


# --- Enrichment Entry Point ---
def apply_score_enrichment(matrix_df: pd.DataFrame, verbose: bool = False) -> pd.DataFrame:
    """
    Enriches a binary AV detection matrix with malicious scoring metadata.

    Args:
        matrix_df (pd.DataFrame): Binary matrix of AV detections.
        verbose (bool): If True, enables diagnostics (disabled in production mode).

    Returns:
        pd.DataFrame: Enriched AV detection matrix.
    """
    if not is_valid_av_matrix(matrix_df):
        return matrix_df

    try:
        score_df = fetch_malicious_score_table()
        if score_df.empty:
            return matrix_df

        enriched = pd.merge(matrix_df, score_df, on="sample_id", how="left", indicator=True)
        enriched = enriched.drop(columns=["_merge"])
        enriched = enrich_score_features.add_derived_score_features(enriched)

        return enriched
    except Exception:
        return matrix_df
