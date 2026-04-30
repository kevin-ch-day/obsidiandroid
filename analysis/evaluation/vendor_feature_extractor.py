# Filename: analysis/evaluation/vendor_feature_extractor.py
# Purpose : Extract and prepare AV vendor classification features for ML analysis pipeline

import pandas as pd
from utils import display_utils as du
from utils import export_manager as em
from analysis.evaluation import evaluate_av_classifications
from data_inspect import inspect_vendor_feature_results
from config import app_config


def extract_vendor_feature_metadata(
    av_pipeline_results: dict,
    samples_df: pd.DataFrame,
    verbose: bool = False
) -> tuple:
    du.print_banner("Vendor Feature Extraction")

    if not _is_valid_pipeline_input(av_pipeline_results):
        return None, None, None, None

    _export_pipeline_results(av_pipeline_results)

    engine_metadata = _generate_engine_metadata_map(av_pipeline_results)
    if not engine_metadata:
        du.print_warning("[VENDOR EXTRACT] No valid engine metadata extracted. Proceeding with defaults.")

    classification_output = _execute_vendor_classification(samples_df, engine_metadata, verbose)
    if classification_output is None:
        return None, None, None, None

    return _finalize_extraction_output(classification_output, verbose)


def _is_valid_pipeline_input(av_pipeline_results: dict) -> bool:
    if not isinstance(av_pipeline_results, dict):
        du.print_error("[VENDOR EXTRACT] Invalid pipeline results type.")
        return False
    if "enriched_matrix" not in av_pipeline_results:
        du.print_error("[VENDOR EXTRACT] 'enriched_matrix' missing from pipeline results.")
        return False
    return True


def _export_pipeline_results(pipeline_data: dict):
    if not bool(getattr(app_config, "ENABLE_AV_PIPELINE_EXCEL_EXPORT", False)):
        du.print_info("[EXPORT] AV pipeline Excel export disabled by config.")
        return
    try:
        du.print_info("[EXPORT] Writing AV pipeline results to Excel...")
        exported_path = em.write_excel_file(pipeline_data, "av_pipeline_outputs.xlsx")
        if exported_path:
            du.print_success("[EXPORT] Pipeline results exported successfully.")
        else:
            du.print_warning("[EXPORT] Pipeline results export skipped or failed.")
    except Exception as e:
        du.print_error(f"[EXPORT] Pipeline export failed: {e}")


def _execute_vendor_classification(samples_df: pd.DataFrame, engine_metadata: dict, verbose: bool) -> dict | None:
    try:
        export_enabled = bool(getattr(app_config, "ENABLE_AV_PIPELINE_EXCEL_EXPORT", False))
        return evaluate_av_classifications.run_vendor_classification_analysis(
            samples_df=samples_df,
            engine_metadata=engine_metadata,
            verbose=verbose,
            export=export_enabled,
        )
    except Exception as e:
        du.print_error(f"[VENDOR EXTRACT] Classification evaluation failed: {e}")
        return None


def _finalize_extraction_output(output: dict, verbose: bool) -> tuple:
    if not isinstance(output, dict):
        du.print_error("[VENDOR EXTRACT] Output is not a dictionary.")
        return None, None, None, None

    vendor_eval_df = output.get("summary_df")
    records_by_vendor = output.get("records_by_vendor")
    parsed_vendor_data = output.get("parsed_data")
    vendor_scorecard_df = vendor_eval_df

    _log_extraction_diagnostics(
        vendor_eval_df,
        parsed_vendor_data,
        vendor_scorecard_df,
        records_by_vendor,
        verbose,
    )

    if any(x is None for x in [vendor_eval_df, parsed_vendor_data, vendor_scorecard_df]):
        du.print_warning("[VENDOR EXTRACT] One or more output components are missing.")
    else:
        du.print_success(f"[VENDOR EXTRACT] Metadata extracted for {len(records_by_vendor)} vendor(s).")
        if verbose:
            inspect_vendor_feature_results.validate_vendor_classification_output(
                output_dict=output,
                verbose=True,
                strict=False,
                interactive=False
            )

    return vendor_eval_df, records_by_vendor, parsed_vendor_data, vendor_scorecard_df


def _log_extraction_diagnostics(
    vendor_eval_df: pd.DataFrame,
    parsed_vendor_data: dict,
    vendor_scorecard_df: pd.DataFrame,
    records_by_vendor: dict,
    verbose: bool,
):
    if not verbose:
        return
    if isinstance(vendor_eval_df, pd.DataFrame):
        du.print_debug(f"[DIAG] summary_df → shape: {vendor_eval_df.shape}")
    else:
        du.print_warning("[DIAG] summary_df missing or invalid.")

    if isinstance(parsed_vendor_data, dict):
        du.print_debug(f"[DIAG] parsed_data keys: {list(parsed_vendor_data.keys())[:5]}")
    else:
        du.print_warning("[DIAG] parsed_data missing or invalid.")

    if isinstance(vendor_scorecard_df, pd.DataFrame):
        du.print_debug(f"[DIAG] scorecard_df → shape: {vendor_scorecard_df.shape}")
    else:
        du.print_warning("[DIAG] scorecard_df missing or invalid.")

    if isinstance(records_by_vendor, dict):
        du.print_debug(f"[DIAG] records_by_vendor → count: {len(records_by_vendor)}")
    elif records_by_vendor is None:
        du.print_warning("[DIAG] records_by_vendor is None.")
    else:
        du.print_warning(f"[DIAG] records_by_vendor type invalid: {type(records_by_vendor)}")


def _generate_engine_metadata_map(av_pipeline_results: dict) -> dict:
    metadata_map = {}

    scores_df = av_pipeline_results.get("engine_scores", None)
    summary_df = av_pipeline_results.get("engine_summary", None)

    if not isinstance(scores_df, pd.DataFrame) or scores_df.empty:
        du.print_warning("[ENGINE META] 'engine_scores' missing or empty — using fallback 'engine_summary'.")
        scores_df = summary_df

    if not isinstance(scores_df, pd.DataFrame) or scores_df.empty:
        du.print_error("[ENGINE META] No valid scoring or summary data available.")
        return metadata_map

    for row in scores_df.to_dict(orient="records"):
        engine_name = row.get("Engine Name") or row.get("engine_name") or row.get("vendor_name")
        if not engine_name:
            continue

        metadata_map[engine_name] = {
            "confidence_score": row.get("ML Weight Score", 0.5),
            "parser_quality": _convert_tier_to_quality(row.get("Detection Tier")),
            "signature_type": row.get("signature_type", "pattern"),
            "is_outlier": bool(row.get("Is Outlier", False)),
            "included": bool(row.get("Included", True)),
            "trusted": bool(row.get("Trusted", True)),
            "active": bool(row.get("Active", True)),
            "tier": row.get("Detection Tier", "unknown"),
            "normalized_score": row.get("Normalized Score", None),
        }

    du.print_info(f"[ENGINE META] Metadata built for {len(metadata_map)} AV engines.")
    return metadata_map


def _convert_tier_to_quality(tier) -> str:
    if isinstance(tier, str):
        tier = tier.strip().lower()
    elif isinstance(tier, (int, float)):
        tier = f"tier {int(tier)}"
    else:
        return "low"

    return {
        "tier 1": "high",
        "tier 2": "medium",
        "tier 3": "medium",
        "tier 4": "low",
        "tier 5": "low"
    }.get(tier, "low")
