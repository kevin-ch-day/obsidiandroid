# Filename: ml_classification/inference/signal_health_checker.py
# Purpose  : Analyze classification record signal quality and identify problematic or weak samples

from typing import List, Dict, Union
from obsidiandroid.vendors.contracts.record_core import VendorClassificationRecord
from obsidiandroid.cli.ui import display as du


def analyze_signal_health(
    records: Union[List[VendorClassificationRecord], Dict[str, List[VendorClassificationRecord]]],
    verbose: bool = True
) -> Dict[str, int]:
    """
    Evaluates a collection of VendorClassificationRecords for quality metrics.
    Returns summary counts of weak vs high-quality indicators.
    """
    try:
        if isinstance(records, dict):
            flattened = [rec for rec_list in records.values() for rec in rec_list]
        elif isinstance(records, list):
            flattened = records
        else:
            if verbose:
                du.print_error("[SIGNAL CHECKER] Input must be list or dict of VendorClassificationRecords.")
            return {}
    except Exception as e:
        if verbose:
            du.print_error(f"[EXCEPTION] Failed to flatten record list: {e}")
        return {}

    stats = {
        "total": len(flattened),
        "high_signal": 0,
        "low_confidence": 0,
        "generic_family": 0,
        "unknown_family": 0,
        "incomplete_labels": 0,
        "valid": 0,
        "signal_strength": 0.0,
    }

    for idx, record in enumerate(flattened):
        if not isinstance(record, VendorClassificationRecord):
            if verbose:
                du.print_warning(f"[ERROR] Object at index {idx} is not a VendorClassificationRecord → {type(record)}")
            continue

        try:
            if callable(record.is_high_signal):
                if record.is_high_signal():
                    stats["high_signal"] += 1
            elif record.is_high_signal:
                stats["high_signal"] += 1

            if record.confidence_score < 0.4:
                stats["low_confidence"] += 1

            if record.is_generic_family:
                stats["generic_family"] += 1

            if (record.family or "").strip().lower() == "unknown":
                stats["unknown_family"] += 1

            if record.validate_record_completeness() != "complete":
                stats["incomplete_labels"] += 1

            if record.is_valid:
                stats["valid"] += 1

        except Exception as e:
            if verbose:
                du.print_warning(f"[EXCEPTION] Failed analyzing record at index {idx}: {e}")
            continue

    if stats["total"]:
        stats["signal_strength"] = round(stats["high_signal"] / stats["total"], 4)

    return stats


def debug_signal_issues(
    records: Union[List[VendorClassificationRecord], Dict[str, List[VendorClassificationRecord]]],
    top_n: int = 10
):
    """
    Prints a ranked list of classification records with the most signal health issues.
    """
    try:
        if isinstance(records, dict):
            flattened = [rec for recs in records.values() for rec in recs]
        elif isinstance(records, list):
            flattened = records
        else:
            du.print_error("[SIGNAL DEBUG] Input must be a list or dict of records.")
            return
    except Exception as e:
        du.print_error(f"[EXCEPTION] Failed to flatten input records: {e}")
        return

    du.print_section("[DEBUG] Top Problematic Classification Records")
    problematic = []

    for idx, record in enumerate(flattened):
        if not isinstance(record, VendorClassificationRecord):
            du.print_warning(f"[WARN] Non-record at index {idx} → {type(record)}")
            continue

        issues = []
        try:
            if not record.is_valid:
                issues.append("invalid")

            if record.confidence_score < 0.4:
                issues.append("low_confidence")

            if record.is_generic_family:
                issues.append("generic_family")

            if (record.family or "").strip().lower() == "unknown":
                issues.append("unknown_family")

            if record.validate_record_completeness() != "complete":
                issues.append("incomplete")

        except Exception as e:
            du.print_warning(f"[EXCEPTION] Issue check failed at index {idx}: {e}")
            continue

        if issues:
            problematic.append((
                record.sample_id,
                record.vendor_name,
                record.family,
                record.confidence_score,
                issues
            ))

    try:
        sorted_problems = sorted(problematic, key=lambda r: r[3])[:top_n]
    except Exception as e:
        du.print_error(f"[EXCEPTION] Problem sorting failed: {e}")
        return

    for sample_id, vendor, family, conf, issues in sorted_problems:
        try:
            issue_list = ", ".join(issues)
            du.print_info(f" - Sample {sample_id} ({vendor}) → Family: '{family}' | Confidence: {conf:.2f} | Issues: {issue_list}")
        except Exception as e:
            du.print_warning(f"[EXCEPTION] Could not print info for {sample_id}: {e}")
