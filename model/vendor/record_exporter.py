# Filename: model/vendor/record_exporter.py
# Description: Export and snapshot utilities for vendor classification records

from dataclasses import asdict
from typing import Dict
from model.vendor.record_core import VendorClassificationRecord


def to_dict(record: VendorClassificationRecord) -> Dict:
    """Serialize the classification record to a dictionary."""
    data = asdict(record)
    data.update({
        "category_vector": ";".join(record.category_vector),
        "threat_tags": ";".join(record.threat_tags),
        "signal_score": record.signal_score,
        "high_signal": record.high_signal,
        "label_validity": record.validate_record_completeness(),
        "confidence_reason": record.confidence_reason,
        "diagnostic_flags": ";".join(record.get_diagnostic_flags())
    })
    return data


def debug_snapshot(record: VendorClassificationRecord) -> Dict:
    """Generate a developer-focused snapshot of key fields for debugging."""
    return {
        "sample_id": record.sample_id,
        "vendor": record.vendor_name,
        "family": record.family,
        "platform": record.platform,
        "malware_type": record.malware_type,
        "threat_class": record.threat_class,
        "signal_score": record.signal_score,
        "confidence": record.confidence_score,
        "confidence_reason": record.confidence_reason,
        "valid": record.is_valid,
        "category_vector": record.category_vector,
        "tags": record.threat_tags,
        "high_signal": record.high_signal,
        "label_validity": record.validate_record_completeness(),
        "flags": record.get_diagnostic_flags()
    }


def get_diagnostic_report(record: VendorClassificationRecord) -> Dict:
    """Generate a report summarizing key classification attributes."""
    return {
        "sample_id": record.sample_id,
        "vendor_name": record.vendor_name,
        "family": record.family,
        "platform": record.platform,
        "malware_type": record.malware_type,
        "threat_class": record.threat_class,
        "variant": record.variant,
        "confidence": record.confidence_score,
        "signal_score": record.signal_score,
        "label_validity": record.validate_record_completeness(),
        "flags": ";".join(record.get_diagnostic_flags()),
        "reason": record.confidence_reason
    }
