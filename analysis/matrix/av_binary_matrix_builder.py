# Filename: av_binary_matrix_builder.py
# Purpose : Standalone phase script to generate AV binary detection matrix for ML processing

import pandas as pd
import re
from database import db_av_engine_verdicts
from obsidiandroid.cli.ui import display as du

METADATA_COLS = {
    "record_id", "sample_id", "timeout", "confirmed_timeout", "failure",
    "type_unsupported", "total_engines", "record_created_at",
    "malicious_pct", "suspicious_pct", "undetected_pct", "harmless_pct", "av_hits",
    "updated_at"
}
REQUIRED_LONG_COLS = {"sample_id", "engine_name", "result"}
MISSING_TOKENS = {"", "none", "null", "n/a"}
EMPTY_TOKENS = {"", "none", "null", "n/a", "undetected", "clean"}

# Labels counted as positive detections in the binary matrix.
MALICIOUS_REGEX = re.compile(
    r"(trojan|backdoor|spy|rat|banker|keylogger|stealer|dropper|"
    r"ransom|clipbank|loader|exploit|malware|virus|phish)",
    flags=re.IGNORECASE,
)
SUSPICIOUS_REGEX = re.compile(
    r"(risktool|adware|grayware|heur|not[- ]?a[- ]?virus|monitor|obfus|pua)",
    flags=re.IGNORECASE,
)

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
    Return 1 when a verdict string indicates malicious/suspicious behavior.

    This prevents false positives from merely non-null labels.
    """
    token = _normalize_result_token(value)
    if token in EMPTY_TOKENS:
        return 0
    if MALICIOUS_REGEX.search(token):
        return 1
    if SUSPICIOUS_REGEX.search(token):
        return 1
    return 0

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
        long_verdicts_df = convert_to_long_format(wide_verdicts_df)
        engine_count = long_verdicts_df["engine_name"].nunique()
        du.print_success(f"[MELT] Success: {len(long_verdicts_df)} rows created across {engine_count} engines.")
    except Exception as e:
        du.print_error(f"[PHASE] Conversion to long-format failed:\n  {e}")
        return pd.DataFrame()

    if long_verdicts_df.empty:
        du.print_error("[PHASE] Long-format DataFrame is empty after conversion.")
        return pd.DataFrame()

    try:
        scan_counts = (
            long_verdicts_df.assign(scanned=long_verdicts_df["result"].map(_is_scanned_result))
            .groupby("engine_name")["scanned"]
            .sum()
            .astype(int)
            .to_dict()
        )

        binary_matrix = (
            long_verdicts_df.assign(value=long_verdicts_df["result"].map(_is_positive_detection))
            .pivot_table(
                index="sample_id",
                columns="engine_name",
                values="value",
                aggfunc="max",
                fill_value=0
            )
            .astype(int)
            .reset_index()
        )
        binary_matrix.attrs["engine_scan_counts"] = scan_counts
    except Exception as e:
        du.print_error(f"[PHASE] Pivot operation failed:\n  {e}")
        du.print_debug(f"[DEBUG] Long-format shape before pivot: {long_verdicts_df.shape}")
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
        cleaned_df[detection_cols] = cleaned_df[detection_cols].astype(int)
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
