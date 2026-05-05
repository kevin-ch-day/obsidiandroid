# Filename: inspect_av_pipeline_results.py
# Purpose : Quick summary and export of AV pipeline results without manual inspection

import os
import pandas as pd
from obsidiandroid.cli.ui import display as du

EXPORT_PIPELINE_SNAPSHOT = "output/av_pipeline_snapshot.xlsx"

def inspect_av_pipeline_results(pipeline_results: dict):
    if not pipeline_results:
        du.print_error("[INSPECT] No pipeline results provided.")
        return

    du.print_banner("AV PIPELINE RESULT CHECKPOINT")

    keys = sorted([k for k, v in pipeline_results.items() if isinstance(v, pd.DataFrame)])

    if not keys:
        du.print_warning("[INSPECT] No valid DataFrames found in pipeline results.")
        return

    # Display DataFrame metadata
    print("\nAvailable Result DataFrames:")
    for idx, key in enumerate(keys, 1):
        df = pipeline_results[key]
        if isinstance(df, pd.DataFrame):
            du.print_info(f"  [{idx}] {key:<20} → {df.shape[0]:>5} rows × {df.shape[1]:<3} cols")

    # Preview content for each DataFrame
    for key in keys:
        df = pipeline_results[key]
        if isinstance(df, pd.DataFrame):
            print("\n" + "=" * 80)
            du.print_header(f"[DATAFRAME] {key}")
            du.print_info(f"Shape: {df.shape[0]} rows × {df.shape[1]} columns")
            print(df.head(5))
            print("=" * 80)

    # Export all to Excel
    _export_all_dataframes(pipeline_results, keys)

# ----------------------------------------------------------------------
# Excel Export Support
# ----------------------------------------------------------------------

def _export_all_dataframes(results: dict, keys: list[str]):
    try:
        with pd.ExcelWriter(EXPORT_PIPELINE_SNAPSHOT, engine="openpyxl") as writer:
            for key in keys:
                df = results.get(key)
                if isinstance(df, pd.DataFrame):
                    sheet_name = key[:31]  # Excel sheet name limit
                    df.to_excel(writer, sheet_name=sheet_name, index=False)

        du.print_info(f"[EXPORT] Pipeline snapshot saved to: {EXPORT_PIPELINE_SNAPSHOT}")
    except Exception as e:
        du.print_warning(f"[EXPORT] Failed to write pipeline snapshot: {e}")
