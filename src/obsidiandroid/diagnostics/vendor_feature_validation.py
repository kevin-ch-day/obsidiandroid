"""Runtime-safe validation for parsed vendor-feature outputs.

The pipeline uses these helpers directly.  Script entrypoints may import the
same functions for interactive inspection, but the production package must not
depend on the repository's ``scripts`` namespace.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from obsidiandroid.cli.ui import display as du


def validate_vendor_classification_output(
    output_dict: dict,
    verbose: bool = False,
    strict: bool = False,
    interactive: bool = False,
) -> tuple | None:
    """Validate the structural contract returned by vendor classification.

    ``interactive`` is retained for caller compatibility.  Runtime validation
    never prompts; it only controls optional bounded console detail.
    """
    if not _is_valid_output_dict(output_dict, strict):
        return None

    summary_df = output_dict["summary_df"]
    records_by_vendor = output_dict["records_by_vendor"]
    parsed_data = output_dict["parsed_data"]
    issues = _collect_validation_issues(
        summary_df=summary_df,
        records_by_vendor=records_by_vendor,
        parsed_data=parsed_data,
        verbose=verbose,
        interactive=interactive,
    )
    if issues:
        _print_validation_issues(issues)
        if strict:
            raise ValueError("Validation failed: " + "; ".join(issues))
        return None

    du.print_success("Vendor output passed validation.")
    return summary_df, records_by_vendor, parsed_data, summary_df


def _is_valid_output_dict(output_dict: object, strict: bool) -> bool:
    if not isinstance(output_dict, dict):
        du.print_error("[VALIDATION] Provided output is not a dictionary.")
        if strict:
            raise ValueError("Expected a dictionary.")
        return False
    missing = [key for key in ("summary_df", "records_by_vendor", "parsed_data") if key not in output_dict]
    if missing:
        du.print_warning(f"[VALIDATION] Missing required keys: {missing}")
        if strict:
            raise KeyError(f"Missing output keys: {missing}")
        return False
    return True


def _collect_validation_issues(
    *,
    summary_df: object,
    records_by_vendor: object,
    parsed_data: object,
    verbose: bool,
    interactive: bool,
) -> list[str]:
    issues: list[str] = []
    if not _validate_dataframe("summary_df", summary_df, min_rows=5, min_cols=3):
        issues.append("summary_df failed validation")
    if not _validate_mapping("records_by_vendor", records_by_vendor):
        issues.append("records_by_vendor missing or invalid")
    if not _inspect_parsed_data(parsed_data, verbose=verbose, interactive=interactive):
        issues.append("parsed_data failed inspection")
    return issues


def _validate_dataframe(label: str, value: object, *, min_rows: int, min_cols: int) -> bool:
    if not isinstance(value, pd.DataFrame):
        du.print_warning(f"[{label}] is not a DataFrame.")
        return False
    if value.empty:
        du.print_warning(f"[{label}] is empty.")
        return False
    if value.shape[0] < min_rows or value.shape[1] < min_cols:
        du.print_warning(f"[{label}] may be undersized: {value.shape[0]} rows, {value.shape[1]} cols")
    return True


def _validate_mapping(label: str, value: object) -> bool:
    if not isinstance(value, Mapping) or not value:
        du.print_warning(f"[{label}] is missing or empty.")
        return False
    return True


def _inspect_parsed_data(parsed_data: object, *, verbose: bool, interactive: bool) -> bool:
    if not isinstance(parsed_data, Mapping) or not parsed_data:
        du.print_warning("[parsed_data] is missing or empty.")
        return False
    record_count = sum(_record_count(value) for value in parsed_data.values())
    if record_count == 0:
        du.print_warning("[INSPECT] No sample records were found across vendors.")
        return False
    if verbose:
        du.print_stat("Vendors Parsed", len(parsed_data))
        du.print_stat("Total Parsed Records", record_count)
        if interactive:
            du.print_note("[INSPECT] Interactive previews are disabled during runtime validation.")
    return True


def _record_count(value: object) -> int:
    if isinstance(value, (list, tuple, set, pd.DataFrame)):
        return len(value)
    return 1 if isinstance(value, Mapping) else 0


def _print_validation_issues(issues: list[str]) -> None:
    du.print_section("Validation Issues")
    for index, issue in enumerate(issues, start=1):
        du.print_note(f"{index}. {issue}")
    du.print_warning("[VALIDATION] Vendor output failed validation.")


__all__ = ["validate_vendor_classification_output"]
