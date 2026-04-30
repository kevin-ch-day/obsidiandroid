# Filename: analysis/pipeline/attach_engine_metadata.py
# Purpose  : Attach AV engine metadata as bottom rows to the binary detection matrix

import pandas as pd
from database import db_av_engine_detection_totals

METADATA_FIELDS = [
    "detection_strategy", "is_trusted_vendor", "is_engine_active",
    "total_scanned", "malicious_count", "suspicious_count", "benign_count",
    "undetected_count", "unknown_count", "family_name_hits",
    "coverage_pct", "malicious_pct", "suspicious_pct", "threat_signal_score"
]

def fetch_engine_metadata(verbose: bool = True) -> pd.DataFrame:
    try:
        engine_df = db_av_engine_detection_totals.get_engine_detection_totals(as_dataframe=True)

        if not isinstance(engine_df, pd.DataFrame) or engine_df.empty:
            raise ValueError("Engine metadata is empty or invalid.")

        required_columns = {"engine_name", "detection_strategy", "is_trusted_vendor", "is_engine_active"}
        missing = required_columns - set(engine_df.columns)
        if missing:
            raise KeyError(f"Missing metadata fields: {sorted(missing)}")

        return engine_df

    except Exception:
        return pd.DataFrame()


def _build_metadata_overlay(
    matrix_columns: list[str], engine_df: pd.DataFrame, verbose: bool
) -> pd.DataFrame:
    """Construct metadata rows aligned to the detection matrix columns."""
    if "engine_name" not in engine_df.columns:
        return pd.DataFrame()

    engine_df = engine_df.set_index("engine_name")
    overlay_rows = {}

    for field in METADATA_FIELDS:
        values = engine_df.get(field)
        if values is None:
            overlay_rows[f"meta::{field}"] = [None] * len(matrix_columns)
        else:
            overlay_rows[f"meta::{field}"] = values.reindex(matrix_columns).tolist()

    meta_df = pd.DataFrame(overlay_rows, index=matrix_columns).T
    meta_df.dropna(how="all", inplace=True)
    return meta_df


def attach_engine_metadata(matrix_df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    engine_df = fetch_engine_metadata(verbose=verbose)
    if engine_df.empty:
        return matrix_df

    matrix_columns = matrix_df.columns.tolist()
    engine_names = set(engine_df["engine_name"])
    matched_columns = [col for col in matrix_columns if col in engine_names]

    if not matched_columns:
        return matrix_df

    meta_df = _build_metadata_overlay(matrix_columns, engine_df, verbose)
    meta_df = meta_df.reindex(columns=matrix_df.columns)
    meta_df.fillna(value=pd.NA, inplace=True)
    meta_df = meta_df.dropna(axis=1, how="all")

    for col in meta_df.columns:
        if col in matrix_df.columns:
            try:
                meta_df[col] = meta_df[col].astype(matrix_df[col].dtype)
            except Exception:
                meta_df[col] = meta_df[col].astype("object")

    if meta_df.empty:
        return matrix_df

    try:
        return pd.concat([matrix_df, meta_df], axis=0, ignore_index=False)
    except Exception:
        return matrix_df
