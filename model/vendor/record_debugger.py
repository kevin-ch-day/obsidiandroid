# Filename: model/vendor/record_debugger.py
# Description: Provides debug display and diagnostic tools for vendor classification records

from typing import Dict
from model.vendor.record_core import VendorClassificationRecord
from utils import display_utils as du
from model.vendor.record_validator import validate_record_completeness


def print_debug_snapshot(record: VendorClassificationRecord):
    """Prints a detailed debug summary of a single record."""
    du.print_subheader(f"[DEBUG] Snapshot: {record.sample_id} ({record.vendor_name})")
    print(f" - Family           : {record.family}")
    print(f" - Platform         : {record.platform}")
    print(f" - Malware Type     : {record.malware_type}")
    print(f" - Threat Class     : {record.threat_class}")
    print(f" - Variant          : {record.variant}")
    print(f" - Composite Tag    : {record.composite_tag}")
    print(f" - Android Target   : {record.is_android}")
    print(f" - Is Valid         : {record.is_valid}")
    print(f" - Known Family     : {record.is_known_family}")
    print(f" - Generic Family   : {record.is_generic_family}")
    print(f" - Confidence Score : {record.confidence_score:.3f}")
    print(f" - Signal Score     : {record.signal_score:.3f}")
    print(f" - High Signal      : {record.high_signal}")
    print(f" - Threat Tags      : {record.threat_tags}")
    print(f" - Category Vector  : {record.category_vector}")
    print(f" - Label Validity   : {validate_record_completeness(record)}")
    print(f" - Diagnostic Flags : {record.get_diagnostic_flags()}")
    print()


def warn_if_weak(record: VendorClassificationRecord):
    """Prints a warning if the record has weak classification signal or missing fields."""
    if not record.is_valid or record.family == "unknown":
        du.print_warning(f"[WARN] Incomplete or weak classification for {record.sample_id} ({record.vendor_name})")
        print_debug_snapshot(record)
