# Filename: ml_classification/vectorization/feature_vendor_extractor.py
# Purpose  : Extract, merge, and enrich vendor feature data for ML vector construction

import pandas as pd
from functools import reduce
from obsidiandroid.cli.ui import display as du


def _normalize_vendor_key(name: str) -> str:
    return (name or "").strip().lower().replace("-", "").replace("_", "")


def _resolve_vendor_frame(parsed_vendor_data: dict, vendor: str):
    if vendor in parsed_vendor_data:
        return vendor, parsed_vendor_data[vendor]

    normalized_map = {
        _normalize_vendor_key(key): key for key in parsed_vendor_data.keys()
    }
    match_key = normalized_map.get(_normalize_vendor_key(vendor))
    if not match_key:
        return None, None
    return match_key, parsed_vendor_data[match_key]


def extract_vendor_fields(parsed_vendor_data, vendor_list, fields):
    extracted = []
    for vendor in vendor_list:
        resolved_key, df = _resolve_vendor_frame(parsed_vendor_data, vendor)
        if df is None:
            du.print_warning(f"[SKIP] Vendor '{vendor}' missing in parsed data.")
            continue

        if "sample_id" not in df.columns:
            du.print_warning(f"[SKIP] Vendor '{vendor}' missing 'sample_id' column.")
            continue

        missing = [f for f in fields if f not in df.columns]
        if missing:
            du.print_warning(f"[WARN] Vendor '{vendor}' missing fields: {missing} - will fill as 'unknown'.")

        for f in fields:
            if f not in df.columns:
                df[f] = "unknown"

        normalized_suffix = _normalize_vendor_key(vendor) or _normalize_vendor_key(resolved_key)
        rename_map = {f: f"{f.lower().replace(' ', '_')}_{normalized_suffix}" for f in fields}
        renamed_df = df[["sample_id"] + fields].copy().rename(columns=rename_map)
        extracted.append(renamed_df)

    return extracted

def merge_vendor_features(frames):
    if not frames:
        du.print_error("[MERGE] No vendor feature frames to merge.")
        return pd.DataFrame()

    try:
        merged = reduce(lambda left, right: pd.merge(left, right, on="sample_id", how="outer"), frames)
        du.print_stat("Merged Feature Shape", f"{merged.shape[0]} samples x {merged.shape[1]} features")
        return merged
    except Exception as e:
        du.print_error(f"[MERGE] Merge failed: {e}")
        return pd.DataFrame()

def extract_enriched_features(enriched_df: pd.DataFrame, columns=None) -> pd.DataFrame:
    if not isinstance(enriched_df, pd.DataFrame) or enriched_df.empty:
        return pd.DataFrame()
    if "sample_id" not in enriched_df.columns:
        du.print_warning("[FEATURE] Enriched matrix missing 'sample_id'.")
        return pd.DataFrame()

    default_cols = [
        "malicious_ratio",
        "detection_density",
        "risk_score",
        "risk_band",
    ]
    cols = columns or default_cols
    keep = [c for c in cols if c in enriched_df.columns]
    if not keep:
        return pd.DataFrame()

    return enriched_df[["sample_id"] + keep].copy()


