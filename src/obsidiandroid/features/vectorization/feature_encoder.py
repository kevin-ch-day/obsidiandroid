# Filename: obsidiandroid/features/vectorization/feature_encoder.py
# Purpose  : Encode merged feature matrix for ML use, supporting categorical and one-hot strategies

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype
from obsidiandroid.cli.ui import display as du


def _handle_low_info_columns(df: pd.DataFrame, verbose: bool) -> None:
    """Warn about columns with little to no variation."""
    if not verbose:
        return
    low_info = [col for col in df.columns if col != "sample_id" and df[col].nunique() <= 1]
    if low_info:
        du.print_warning(f"[ENCODE] Low-information fields detected: {low_info}")


def encode_features(
    df: pd.DataFrame,
    encoding: str = "category",
    verbose: bool = True,
    skip_numeric: bool = False
) -> pd.DataFrame:
    """
    Encodes features in the given DataFrame using either categorical or one-hot encoding.

    Args:
        df (pd.DataFrame): Raw feature matrix with "sample_id" column.
        encoding (str): Encoding strategy: "category" or "onehot".
        verbose (bool): Print debug output.
        skip_numeric (bool): Skip encoding for numeric columns.

    Returns:
        pd.DataFrame: Encoded feature matrix indexed by ``sample_id`` (index name set explicitly).
    """
    if df.empty:
        du.print_error("[ENCODE] Empty DataFrame — skipping encoding.")
        return pd.DataFrame()

    if "sample_id" not in df.columns:
        du.print_error("[ENCODE] Missing 'sample_id' column — cannot encode features.")
        return pd.DataFrame()

    encoder_mappings = {}

    try:
        if encoding == "category":
            df = df.copy()
            for col in df.columns:
                if col == "sample_id":
                    df[col] = df[col].fillna("unknown")
                    continue
                if skip_numeric and is_numeric_dtype(df[col]):
                    missing_value = False if is_bool_dtype(df[col]) else 0
                    df[col] = df[col].fillna(missing_value)
                else:
                    cat_series = df[col].fillna("unknown").astype("category")
                    df[col] = cat_series.cat.codes
                    encoder_mappings[col] = {
                        str(category): int(code)
                        for code, category in enumerate(cat_series.cat.categories.tolist())
                    }

            _handle_low_info_columns(df, verbose)
            encoded = df.set_index("sample_id")
            encoded.index.name = "sample_id"
            encoded.attrs["encoder_mappings"] = encoder_mappings
            return encoded

        elif encoding == "onehot":
            df = df.fillna("unknown").set_index("sample_id")
            encoded = pd.get_dummies(df, drop_first=True)
            encoded.index.name = "sample_id"
            return encoded

        else:
            raise ValueError(f"Unsupported encoding strategy: '{encoding}' — must be 'category' or 'onehot'.")

    except Exception as e:
        du.print_error(f"[ENCODE] Feature encoding failed: {type(e).__name__} — {e}")
        return pd.DataFrame()
