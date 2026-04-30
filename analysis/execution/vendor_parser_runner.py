# Filename: analysis/execution/vendor_parser_runner.py
# Purpose : Executes a single vendor parser and builds structured classification records with minimal production logs

import pandas as pd
import traceback
from typing import Tuple, List, Dict, Any, Optional

from analysis.execution import vendor_classification_processor
from utils import display_utils as du


def execute_vendor_parser(
    vendor: str,
    meta: Dict[str, Any],
    merged_df: pd.DataFrame,
    engine_meta: Dict[str, Any],
    verbose: bool = False,
    debug: bool = False  # Ignored in production
) -> Tuple[Optional[pd.DataFrame], List[Any], Dict[str, Any], List[str], Dict[str, Any]]:

    parser_func = meta.get("func")
    parser_mode = meta.get("type", "column")

    if not callable(parser_func):
        du.print_warning(f"[SKIP] No valid parser function provided for vendor: '{vendor}'")
        return _return_empty_result(len(merged_df))

    if verbose:
        _validate_sample_input(vendor, parser_func, parser_mode, merged_df)

    try:
        result = vendor_classification_processor.process_vendor_classification(
            vendor=vendor,
            meta=meta,
            merged_df=merged_df,
            engine_metadata=engine_meta
        )
        if verbose:
            du.print_info(f"[OK] Parser completed for vendor: {vendor}")
        return result

    except Exception as e:
        du.print_error(f"[FAILURE] Parser crash for vendor '{vendor}': {e}")
        _print_crash_hint(e)
        return _return_empty_result(len(merged_df))


def _validate_sample_input(vendor: str, parser_func: Any, parser_mode: str, merged_df: pd.DataFrame):
    try:
        sample = (
            merged_df.iloc[0]
            if parser_mode == "row"
            else merged_df[vendor].dropna().astype(str).iloc[0]
        )
        parser_func(sample)  # Attempt basic invocation for structural check
    except IndexError:
        du.print_warning(f"[VALIDATE] No usable input rows found for vendor: '{vendor}'")
    except Exception:
        du.print_warning(f"[VALIDATE] Input validation failed for vendor: '{vendor}'")


def _print_crash_hint(error: Exception):
    """
    Attempt to provide intelligent hints for common parser failures.
    """
    hints = {
        "most_common": "You may be calling `.most_common()` on a dict instead of a Counter.",
        "attribute": "Missing object property — check if the parser returns a ParsedLabelMetadata.",
        "dict": "Parser returned a raw dict but a class object was expected.",
        "type": "Type mismatch — check for unexpected `None` or field values."
    }

    error_str = str(error).lower()
    for keyword, hint in hints.items():
        if keyword in error_str:
            du.print_warning(f"[HINT] {hint}")
            break


def _return_empty_result(total: int) -> Tuple[None, List[Any], Dict[str, Any], List[str], Dict[str, Any]]:
    return None, [], {}, [], {
        "total": total,
        "parsed": 0,
        "success_rate": 0.0
    }
