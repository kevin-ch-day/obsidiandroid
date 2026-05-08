# Filename: evaluate_av_classifications.py
# Description: Orchestrates AV vendor classification analysis and optional export

import pandas as pd

from obsidiandroid.cli.ui import display as du
from obsidiandroid.evaluation import vendor_classification_inspector as inspector
from obsidiandroid.evaluation import parse_vendor_classifications
from obsidiandroid.reporting import export_manager as em


def run_vendor_classification_analysis(
    samples_df: pd.DataFrame,
    engine_metadata: dict = None,
    export: bool = True,
    verbose: bool = False,
) -> dict:
    """
    Orchestrates AV vendor classification analysis:
    - Parses vendor labels
    - Scores classification results
    - Optionally exports summary output
    """
    du.print_section("Running Vendor Classification Analysis")

    parsed_data, summary_df, records_by_vendor, flat_df = parse_vendor_classifications(
        samples_df=samples_df,
        engine_metadata=engine_metadata,
        verbose=verbose,
    )

    # === Failure Handling: No Scoring Results ===
    if summary_df.empty:
        du.print_error("[CLASSIFY] Vendor scoring failed — no classification results.")
        return _empty_result_payload()

    # === Output Summary ===
    inspector.print_summary_table(summary_df, verbose=verbose)

    # === Optional Export ===
    if export:
        _export_results(parsed_data, summary_df)

    return {
        "parsed_data": parsed_data,
        "summary_df": summary_df,
        "records_by_vendor": records_by_vendor,
        "full_flat_dataframe": flat_df,
    }


def _export_results(parsed_data: dict, summary_df: pd.DataFrame):
    """
    Handles export of vendor classification outputs.
    """
    if summary_df.empty or not parsed_data:
        du.print_warning("[EXPORT] No valid classification results to export.")
        return

    try:
        exported_path = em.export_vendor_results(parsed_data, summary_df)
        if exported_path:
            du.print_success("[EXPORT] Vendor results exported successfully.")
        else:
            du.print_warning("[EXPORT] Vendor results export skipped or failed.")
    except Exception as e:
        du.print_warning(f"[EXPORT] Failed to export vendor results: {e}")


def _empty_result_payload() -> dict:
    """
    Returns an empty result dictionary to ensure downstream code doesn't break.
    """
    return {
        "parsed_data": {},
        "summary_df": pd.DataFrame(),
        "records_by_vendor": {},
        "full_flat_dataframe": pd.DataFrame(),
    }
