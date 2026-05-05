# Filename: model/vendor/record_validator.py
# Description: Validates vendor classification records and performs batch-level diagnostics

from typing import List, Dict
from .record_core import VendorClassificationRecord
from obsidiandroid.cli.ui import display as du


def validate_record_completeness(record: VendorClassificationRecord) -> str:
    """
    Checks if all core classification fields are populated with meaningful values.
    Returns 'complete' if valid, otherwise 'incomplete'.
    """
    required_fields = {
        "family": record.family,
        "platform": record.platform,
        "malware_type": record.malware_type,
        "threat_class": record.threat_class
    }

    for field_name, value in required_fields.items():
        value_normalized = str(value or "").strip().lower()
        if value_normalized in {"", "unknown"}:
            du.print_debug(f"[INCOMPLETE] {record.sample_id} field '{field_name}' is missing or unknown: '{value}'")
            return "incomplete"

    return "complete"


def is_family_unknown(record: VendorClassificationRecord) -> bool:
    """
    Returns True if the family field is missing or explicitly set to 'unknown'.
    """
    value = str(record.family or "").strip().lower()
    return value == "unknown"


def is_any_critical_field_empty(record: VendorClassificationRecord) -> bool:
    """
    Returns True if any of the core identifying fields are missing or empty.
    Used for data hygiene diagnostics.
    """
    critical_fields = [
        record.sample_id,
        record.vendor_name,
        record.original_label
    ]
    return any(not (str(f or "").strip()) for f in critical_fields)


def validate_batch(records: List[VendorClassificationRecord]) -> Dict[str, int]:
    """
    Performs batch-level validation on a list of records.
    Returns statistics including totals and specific failure conditions.
    """
    stats = {
        "total": len(records),
        "complete": 0,
        "incomplete": 0,
        "unknown_family": 0,
        "missing_core_fields": 0
    }

    for record in records:
        # Track completeness of core classification fields
        if validate_record_completeness(record) == "complete":
            stats["complete"] += 1
        else:
            stats["incomplete"] += 1

        # Track weak or unresolved family field
        if is_family_unknown(record):
            stats["unknown_family"] += 1

        # Track missing critical ID or metadata fields
        if is_any_critical_field_empty(record):
            stats["missing_core_fields"] += 1

    du.print_info(f"[VALIDATION] Batch of {stats['total']} records analyzed.")
    du.print_info(f" - Complete           : {stats['complete']}")
    du.print_info(f" - Incomplete         : {stats['incomplete']}")
    du.print_info(f" - Unknown Family     : {stats['unknown_family']}")
    du.print_info(f" - Missing ID Fields  : {stats['missing_core_fields']}")

    return stats
