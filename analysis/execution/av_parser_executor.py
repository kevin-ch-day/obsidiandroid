# Filename: analysis/execution/av_parser_executor.py
# Purpose  : Executes structured parsing of AV labels and builds classification records

import pandas as pd
from typing import Tuple, Dict, List, Any
from analysis.execution import vendor_parser_runner
from obsidiandroid.cli.ui import display as du


def parse_all_vendors(
    merged_df: pd.DataFrame,
    vendor_map: dict,
    metadata_lookup: dict = None,
    verbose: bool = False
) -> Tuple[
    Dict[str, pd.DataFrame],
    List[dict],
    Dict[str, List[Any]],
    pd.DataFrame,
    List[str]
]:
    """
    Run all vendor parsers on the provided AV scan results.

    Returns:
        - vendor_results: parsed DataFrames keyed by vendor name
        - summary_rows: one summary dict per vendor
        - records_by_vendor: original record objects keyed by vendor
        - result_df: flattened DataFrame of all parsed records
        - parsing_errors: combined list of warnings/errors
    """
    available_columns = set(merged_df.columns)
    vendor_results: Dict[str, pd.DataFrame] = {}
    records_by_vendor: Dict[str, List[Any]] = {}
    flat_record_list: List[dict] = []
    summary_rows: List[dict] = []
    parsing_errors: List[str] = []
    skipped_vendors: List[str] = []

    for vendor, meta in vendor_map.items():
        parser_mode = meta.get("type", "column")
        column_name = meta.get("column_name", vendor)

        if parser_mode != "row" and column_name not in available_columns:
            skipped_vendors.append(vendor)
            if verbose:
                du.print_debug(f"[SKIP] Vendor '{vendor}' not in columns and not row-based.")
            continue

        engine_meta = metadata_lookup.get(column_name, {}) if metadata_lookup else {}
        meta_for_runner = dict(meta)
        meta_for_runner["display_name"] = vendor

        try:
            parsed_df, record_list, summary, errors, stats = vendor_parser_runner.execute_vendor_parser(
                vendor=column_name,
                meta=meta_for_runner,
                merged_df=merged_df,
                engine_meta=engine_meta,
                verbose=verbose
            )
        except Exception as e:
            parsing_errors.append(f"[ERROR] Parser crashed for '{vendor}': {e}")
            du.print_error(f"[ERROR] Parser crashed for '{vendor}': {e}")
            continue

        if not isinstance(parsed_df, pd.DataFrame) or parsed_df.empty:
            if verbose:
                du.print_warning(f"[EMPTY] No parsed records for vendor: {vendor}")
            continue

        vendor_results[vendor] = parsed_df
        records_by_vendor[vendor] = record_list or []
        flat_record_list.extend(rec.to_dict() for rec in record_list or [])
        summary_rows.append(summary or {})
        parsing_errors.extend(errors or [])

    if skipped_vendors and verbose:
        du.print_warning(f"[SKIPPED] Vendors skipped due to missing columns: {len(skipped_vendors)}")
        for v in skipped_vendors:
            du.print_debug(f"  - {v}")

    result_df = pd.DataFrame(flat_record_list)
    return vendor_results, summary_rows, records_by_vendor, result_df, parsing_errors
