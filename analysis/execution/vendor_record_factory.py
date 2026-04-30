# Filename: analysis/execution/vendor_record_factory.py
# Description: Factory for building structured AV classification records with modular validation and diagnostics.

import pandas as pd
from typing import Callable, Dict, Any, Optional, Union, Mapping

from model.vendor.record_core import VendorClassificationRecord
from model.parsing.parsed_label_metadata import ParsedLabelMetadata
from utils import display_utils as du

INVALID_LABEL_TOKENS = {"", "none", "nan", "null"}


def create_vendor_record(
    row: Mapping[str, Any],
    vendor_name: str,
    parser_func: Callable,
    parser_mode: str = "column",
    engine_metadata: Optional[dict] = None
) -> Dict[str, Any]:
    """
    Core interface for building a structured classification record for a single sample.
    Returns a dict with keys: record, label, true_family, error
    """
    label = _get_clean_label(row, vendor_name)
    true_family = _get_true_family(row)

    if not _label_is_valid(label):
        return _build_result(None, label, true_family, "LabelMissingOrEmpty")

    if not callable(parser_func):
        du.print_error(f"[ERROR] Parser function is not callable for vendor: {vendor_name}")
        return _build_result(None, label, true_family, "InvalidParserFunction")

    metadata = _parse_label(parser_func, parser_mode, label, row, engine_metadata)
    if isinstance(metadata, str):
        du.print_warning(f"[FAIL] {vendor_name} → {metadata} (label={label})")
        return _build_result(None, label, true_family, metadata)

    if not isinstance(metadata, ParsedLabelMetadata):
        du.print_warning(f"[FAIL] {vendor_name} → Invalid metadata structure (not ParsedLabelMetadata).")
        return _build_result(None, label, true_family, "ParsedLabelInvalidFormat")

    record = _construct_record(row, vendor_name, label, metadata, true_family)
    if isinstance(record, str):
        du.print_warning(f"[FAIL] {vendor_name} → {record} (label={label})")
        return _build_result(None, label, true_family, record)

    return _build_result(record, label, true_family)


# ------------------------
# Internal Utilities
# ------------------------

def _get_clean_label(row: Mapping[str, Any], vendor: str) -> str:
    raw_label = row.get(vendor, "")
    if pd.isna(raw_label):
        return ""
    cleaned = str(raw_label).strip()
    return "" if cleaned.lower() in INVALID_LABEL_TOKENS else cleaned

def _get_true_family(row: Mapping[str, Any]) -> str:
    for col in ("family_canonical", "family_name", "family_label_raw", "family_id"):
        if col in row and str(row.get(col, "")).strip():
            return str(row.get(col, "")).strip().lower()
    return ""

def _label_is_valid(label: str) -> bool:
    return bool(label and label.strip() and label.strip().lower() not in INVALID_LABEL_TOKENS)

def _parse_label(
    parser_func: Callable,
    mode: str,
    label: str,
    row: Mapping[str, Any],
    metadata: Optional[dict]
) -> Union[ParsedLabelMetadata, str]:
    """
    Executes the parser function and returns a ParsedLabelMetadata object if successful.
    Handles both legacy dict outputs and updated ParsedLabelMetadata outputs.
    Returns a string error message on failure.
    """
    try:
        # Run the parser based on the declared mode
        raw_output = parser_func(row, metadata) if mode == "row" else parser_func(label, metadata)

        if raw_output is None:
            return "ParserReturnedNone"

        # If parser returned a valid ParsedLabelMetadata instance, return as is
        if isinstance(raw_output, ParsedLabelMetadata):
            return raw_output

        # If parser returned a dict, try converting it to ParsedLabelMetadata
        if isinstance(raw_output, dict):
            return ParsedLabelMetadata.from_dict(raw_output)

        # Catch all other unexpected return types
        return f"ParserReturnedInvalidType: {type(raw_output).__name__}"

    except Exception as e:
        return f"ParserError: {type(e).__name__} - {e}"

def _construct_record(
    row: Mapping[str, Any],
    vendor: str,
    label: str,
    metadata: ParsedLabelMetadata,
    true_family: str
) -> Union[VendorClassificationRecord, str]:
    try:
        return VendorClassificationRecord.from_metadata(
            sample_id=row.get("sample_id"),
            vendor_name=vendor,
            original_label=label,
            metadata=metadata,
            known_family=true_family
        )
    except Exception as e:
        return f"RecordInitError: {type(e).__name__} - {e}"

def _build_result(
    record: Optional[VendorClassificationRecord],
    label: str,
    true_family: str,
    error: Optional[str] = None
) -> Dict[str, Any]:
    return {
        "record": record,
        "label": label,
        "true_family": true_family,
        "error": error
    }
