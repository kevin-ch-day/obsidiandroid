# Filename: analysis\data_inspect\inspect_vendor_feature_results.py
# Purpose  : Modular validation and diagnostics for vendor parsing output

import pandas as pd
from utils import display_utils as du
from . import inspect_parsed_data

def validate_vendor_classification_output(
    output_dict: dict,
    verbose: bool = False,
    strict: bool = False,
    interactive: bool = False
) -> tuple | None:

    if not _is_valid_output_dict(output_dict, strict):
        return None

    summary_df = output_dict["summary_df"]
    records_by_vendor = output_dict["records_by_vendor"]
    parsed_data = output_dict["parsed_data"]
    scorecard_df = summary_df

    issues = _run_all_validations(summary_df, records_by_vendor, parsed_data, verbose, interactive)

    if issues:
        _print_validation_issues(issues)
        if strict:
            raise ValueError("Validation failed: " + "; ".join(issues))
        return None

    du.print_success("Vendor output passed validation.")
    return summary_df, records_by_vendor, parsed_data, scorecard_df

def _is_valid_output_dict(output_dict: dict, strict: bool) -> bool:
    if not isinstance(output_dict, dict):
        du.print_error("[VALIDATION] Provided output is not a dictionary.")
        if strict:
            raise ValueError("Expected a dictionary.")
        return False

    required_keys = ["summary_df", "records_by_vendor", "parsed_data"]
    missing = [k for k in required_keys if k not in output_dict]
    if missing:
        du.print_warning(f"[VALIDATION] Missing required keys: {missing}")
        if strict:
            raise KeyError(f"Missing output keys: {missing}")
        return False

    return True


def _run_all_validations(
    summary_df: pd.DataFrame,
    records_by_vendor: dict,
    parsed_data: dict,
    verbose: bool,
    interactive: bool
) -> list:
    issues = []

    if not _validate_dataframe("summary_df", summary_df, min_rows=5, min_cols=3):
        issues.append("summary_df failed validation")

    if not _validate_dict("records_by_vendor", records_by_vendor):
        issues.append("records_by_vendor missing or invalid")

    if not _validate_parsed_data(parsed_data, verbose, interactive):
        issues.append("parsed_data failed inspection")

    return issues

def _validate_dataframe(label: str, df: pd.DataFrame, min_rows: int = 1, min_cols: int = 1) -> bool:
    if not isinstance(df, pd.DataFrame):
        du.print_warning(f"[{label}] is not a DataFrame.")
        return False
    if df.empty:
        du.print_warning(f"[{label}] is empty.")
        return False
    if df.shape[0] < min_rows or df.shape[1] < min_cols:
        du.print_warning(f"[{label}] may be undersized: {df.shape[0]} rows, {df.shape[1]} cols")
    return True


def _validate_dict(label: str, d: dict) -> bool:
    if not isinstance(d, dict) or not d:
        du.print_warning(f"[{label}] is missing or empty.")
        return False
    return True


def _validate_parsed_data(parsed_data: dict, verbose: bool, interactive: bool) -> bool:
    if not isinstance(parsed_data, dict) or not parsed_data:
        du.print_warning("[parsed_data] is missing or empty.")
        return False
    return inspect_parsed_data.inspect(parsed_data, verbose=verbose, interactive=interactive)

def _print_validation_issues(issues: list):
    du.print_section("Validation Issues")
    for idx, issue in enumerate(issues, 1):
        du.print_note(f"{idx}. {issue}")
    du.print_warning("[VALIDATION] Vendor output failed validation.")
