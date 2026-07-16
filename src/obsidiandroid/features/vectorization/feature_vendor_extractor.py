# Filename: obsidiandroid/features/vectorization/feature_vendor_extractor.py
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

        normalized_suffix = _normalize_vendor_key(vendor) or _normalize_vendor_key(resolved_key)
        rename_map = {f: f"{f.lower().replace(' ', '_')}_{normalized_suffix}" for f in fields}
        # ``reindex`` supplies absent parser fields without mutating the
        # shared vendor frame, which may be reused by diagnostics or a later
        # feature configuration in the same run.
        renamed_df = df.reindex(columns=["sample_id", *fields], fill_value="unknown").copy()
        renamed_df = renamed_df.rename(columns=rename_map)
        extracted.append(renamed_df)

    return extracted

def merge_vendor_features(frames):
    if not frames:
        du.print_error("[MERGE] No vendor feature frames to merge.")
        return pd.DataFrame()

    try:
        merged = reduce(lambda left, right: pd.merge(left, right, on="sample_id", how="outer"), frames)
        from obsidiandroid.evaluation.ml_terminal_presentation import should_suppress_ablation_feature_build_terminal

        if not should_suppress_ablation_feature_build_terminal():
            # ``sample_id`` is the join key, not a predictive feature.  In the
            # leakage-safe headline contract there may deliberately be no
            # lexical vendor columns at this point; enrichment is added later
            # by the vector builder.  Reporting the key as one feature made a
            # healthy zero-column pre-enrichment matrix look malformed.
            feature_count = max(0, len(merged.columns) - int("sample_id" in merged.columns))
            if feature_count:
                du.print_stat(
                    "Merged Vendor Features",
                    f"{len(merged)} samples x {feature_count} lexical feature columns",
                )
            else:
                du.print_info(
                    "[FEATURE BUILD] Vendor lexical columns: 0 (policy-disabled); "
                    "continuing to enrichment."
                )
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
