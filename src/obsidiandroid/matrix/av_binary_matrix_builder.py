# Filename: av_binary_matrix_builder.py
# Purpose : Standalone phase script to generate AV binary detection matrix for ML processing

import pandas as pd

from obsidiandroid.cli.ui import display as du
from obsidiandroid.database import db_av_engine_verdicts
from obsidiandroid.database.verdict_semantics import (
    NON_DETECTION_TOKENS,
    VERDICT_METADATA_COLUMNS,
    is_positive_detection_label,
)

METADATA_COLS = VERDICT_METADATA_COLUMNS
REQUIRED_LONG_COLS = {"sample_id", "engine_name", "result"}
MISSING_TOKENS = {"", "none", "null", "n/a"}

def is_valid_verdict_df(df: pd.DataFrame) -> bool:
    if df.empty:
        du.print_warning("[CHECK] Input DataFrame is empty.")
        return False
    if "sample_id" not in df.columns:
        du.print_error("[CHECK] Missing required column: sample_id")
        return False
    return True


def get_av_engine_columns(df: pd.DataFrame) -> list:
    return [col for col in df.columns if col not in METADATA_COLS]


def validate_long_format(df: pd.DataFrame) -> bool:
    missing = REQUIRED_LONG_COLS - set(df.columns)
    if missing:
        du.print_error(f"[CHECK] Long-format DataFrame missing columns: {missing}")
        return False
    return True

def convert_to_long_format(verdicts_df: pd.DataFrame) -> pd.DataFrame:
    if not is_valid_verdict_df(verdicts_df):
        return pd.DataFrame()

    engine_cols = get_av_engine_columns(verdicts_df)
    if not engine_cols:
        du.print_error("[MELT] No AV engine columns found for melting.")
        return pd.DataFrame()

    long_df = verdicts_df.melt(
        id_vars=["sample_id"],
        value_vars=engine_cols,
        var_name="engine_name",
        value_name="result"
    ).dropna(subset=["result"])

    if not validate_long_format(long_df):
        return pd.DataFrame()

    return long_df


def _normalize_result_token(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().lower()


def _is_scanned_result(value: object) -> bool:
    """
    True when a verdict value indicates the engine produced a result.

    Note: 'undetected' is considered scanned (but not malicious).
    """
    token = _normalize_result_token(value)
    return token not in MISSING_TOKENS


def _is_positive_detection(value: object) -> int:
    """
    Return 1 when a vendor emitted any positive detection label.

    The wide verdict table is not a boolean matrix; engines emit strings such
    as ``Detected``, ``unsafe``, family names, or generic threat labels. The
    binary matrix should treat any non-benign, non-undetected token as a
    positive detection.
    """
    return is_positive_detection_label(value)

def _generate_av_binary_matrix(samples_df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    if samples_df is None or samples_df.empty:
        du.print_error("[PHASE] Input DataFrame is empty or None.")
        return pd.DataFrame()

    if "sample_id" not in samples_df.columns:
        du.print_error("[PHASE] 'sample_id' column missing in input DataFrame.")
        return pd.DataFrame()

    sample_ids = samples_df["sample_id"].tolist()

    wide_verdicts_df = db_av_engine_verdicts.fetch_verdicts_simple_ids(sample_ids, verbose=verbose)
    if wide_verdicts_df.empty:
        du.print_error("[PHASE] No AV verdicts retrieved from database.")
        return pd.DataFrame()
    
    try:
        # The source is already a sample × engine matrix.  Melting roughly
        # 215k observed cells and immediately pivoting them back to the same
        # shape creates avoidable peak memory and dataframe work.  Construct
        # the binary matrix directly, retaining the former pivot semantics for
        # duplicate sample rows and all-null samples.
        engine_cols = get_av_engine_columns(wide_verdicts_df)
        if not engine_cols:
            du.print_error("[PHASE] No AV engine columns found in verdict matrix.")
            return pd.DataFrame()
        verdict_values = wide_verdicts_df[engine_cols]
        present = verdict_values.notna()
        normalized = verdict_values.astype(str).apply(lambda col: col.str.strip().str.lower())
        scan_counts = (
            (present & ~normalized.isin(MISSING_TOKENS))
            .sum(axis=0)
            .astype(int)
            .to_dict()
        )
        binary_values = (present & ~normalized.isin(NON_DETECTION_TOKENS)).astype("int8")
        # ``melt(...).dropna(...).pivot_table(...)`` omitted a sample when all
        # of its engine verdict cells were null. Keep that existing population
        # contract while eliminating the temporary long-form dataframe.
        binary_matrix = binary_values.loc[present.any(axis=1)].copy()
        binary_matrix.insert(0, "sample_id", wide_verdicts_df.loc[binary_matrix.index, "sample_id"].to_numpy())
        binary_matrix = (
            binary_matrix.groupby("sample_id", as_index=False, sort=True)[engine_cols]
            .max()
            .astype({column: "int8" for column in engine_cols})
        )
        # Preserve the column-index name emitted by the previous pivot-table path.
        binary_matrix.columns.name = "engine_name"
        binary_matrix.attrs["engine_scan_counts"] = scan_counts
        observed_cells = int(present.to_numpy(dtype=bool).sum())
        du.print_success(
            f"[VERDICTS] Success: {observed_cells} observed cells across {len(engine_cols)} engines."
        )
    except Exception as e:
        du.print_error(f"[PHASE] Binary matrix construction failed:\n  {e}")
        du.print_debug(f"[DEBUG] Wide verdict shape: {wide_verdicts_df.shape}")
        return pd.DataFrame()

    return binary_matrix

def _validate_input_dataframe(df: pd.DataFrame, verbose: bool = True) -> bool:
    if df is None or df.empty:
        if verbose:
            du.print_error("[VALIDATION] Input DataFrame is empty or None.")
        return False

    if "sample_id" not in df.columns:
        if verbose:
            du.print_error("[VALIDATION] Missing required column: 'sample_id'.")
        return False

    return True

def _postprocess_and_clean_matrix(matrix_df: pd.DataFrame) -> pd.DataFrame:
    cleaned_df = matrix_df.copy()
    cleaned_df.columns = [col.strip() for col in cleaned_df.columns]

    drop_cols = [col for col in ["engine_name", "label", "value"] if col in cleaned_df.columns]
    if drop_cols:
        du.print_warning(f"[CLEANUP] Removing unexpected columns: {drop_cols}")
        cleaned_df = cleaned_df.drop(columns=drop_cols)

    detection_cols = [col for col in cleaned_df.columns if col != "sample_id"]
    cleaned_df[detection_cols] = cleaned_df[detection_cols].fillna(0)

    try:
        # Detection features are strictly binary.  Preserve compact storage
        # through cleanup instead of widening every engine column to int64.
        cleaned_df[detection_cols] = cleaned_df[detection_cols].astype("int8")
    except Exception as e:
        du.print_error(f"[CLEANUP ERROR] Failed to convert detection columns to int:\n  {e}")
        return pd.DataFrame()

    bad_cols = []
    for col in detection_cols:
        unique_vals = set(cleaned_df[col].unique())
        if not unique_vals.issubset({0, 1}):
            bad_cols.append((col, sorted(unique_vals)))

    if bad_cols:
        du.print_warning(f"[CLEANUP] Found {len(bad_cols)} columns with non-binary values.")
        for col, vals in bad_cols:
            du.print_debug(f" - {col}: {vals}")
        return pd.DataFrame()

    return cleaned_df

def generate_binary_detection_matrix(samples_df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    if not _validate_input_dataframe(samples_df, verbose=verbose):
        return pd.DataFrame()

    if verbose:
        du.print_info(f"[INIT] Generating binary detection matrix for {len(samples_df)} samples...")

    try:
        matrix_df = _generate_av_binary_matrix(samples_df, verbose=verbose)
        if matrix_df.empty:
            du.print_warning("[PHASE] Binary matrix generation returned an empty result.")
            return pd.DataFrame()

        matrix_df = _postprocess_and_clean_matrix(matrix_df)
        if matrix_df.empty:
            du.print_error("[ABORT] Post-processing failed — binary matrix invalid after cleanup.")
            return pd.DataFrame()

    except Exception as e:
        du.print_error(f"[FATAL] Binary matrix generation encountered an error:\n  {e}")
        return pd.DataFrame()

    return matrix_df
