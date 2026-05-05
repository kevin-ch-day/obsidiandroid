# Filename: analysis/execution/vendor_classification_processor.py
# Purpose : Process AV vendor labels into structured records with minimal production-ready logging

import pandas as pd
from typing import List, Tuple, Callable, Dict, Any, Mapping

from model.vendor.record_core import VendorClassificationRecord
from obsidiandroid.cli.ui import display as du
from analysis.execution import vendor_record_factory
from analysis.evaluation import vendor_summary_builder

def process_vendor_classification(
    vendor: str,
    meta: Dict[str, Any],
    merged_df: pd.DataFrame,
    engine_metadata: Dict[str, Any] = None,
    debug_mode: bool = False
) -> Tuple[pd.DataFrame, List[VendorClassificationRecord], Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Parses all labels for a single AV vendor and produces structured records and statistics.
    Returns:
        - Parsed row DataFrame
        - List of VendorClassificationRecord objects
        - Vendor summary dictionary
        - Error logs
        - Diagnostic statistics
    """
    parser_func: Callable = meta.get("func")
    parser_mode: str = meta.get("type", "column")

    if not callable(parser_func):
        du.print_error(f"[VENDOR_PARSER] Vendor '{vendor}' missing valid parser function.")
        return None, [], {}, [], _finalize_stats({"total": len(merged_df), "parsed": 0})

    stats = _initialize_vendor_stats()
    parsed_rows, record_list, error_log, diagnostic_cases = [], [], [], []

    if debug_mode:
        du.print_info(f"[VENDOR_PARSER] Starting parser for: {vendor} ({len(merged_df)} rows)")

    row_records = merged_df.to_dict(orient="records")
    total_rows = len(row_records)

    for idx, row_data in enumerate(row_records):
        stats["total"] += 1

        try:
            result = vendor_record_factory.create_vendor_record(
                row_data, vendor, parser_func, parser_mode, engine_metadata
            )
        except Exception as e:
            error_log.append(_build_error_log(vendor, row_data, f"Crash: {e}"))
            if debug_mode:
                du.print_warning(f"[VENDOR_PARSER] EXCEPTION in '{vendor}' at row {idx}: {e}")
            continue

        error = result.get("error")
        if error == "LabelMissingOrEmpty":
            continue
        elif error:
            error_log.append(_build_error_log(vendor, row_data, error))
            continue

        record: VendorClassificationRecord = result.get("record")
        if not record:
            continue

        stats["parsed"] += 1
        record_list.append(record)
        parsed_rows.append(vendor_summary_builder.build_parsed_row(record, result.get("true_family")))
        _update_classification_stats(stats, record, result.get("label"))

        if debug_mode and (stats["total"] % 100 == 0 or stats["total"] == total_rows):
            du.print_info(f"[VENDOR_PARSER] {vendor} Progress: {stats['parsed']}/{stats['total']}")

    if stats["parsed"] == 0:
        du.print_warning(f"[VENDOR_PARSER] {vendor} — No successful parses from {stats['total']} rows.")
        return None, [], {}, error_log, _finalize_stats(stats)

    stats["diagnostic_cases"] = len(diagnostic_cases)

    summary = vendor_summary_builder.build_vendor_summary(
        vendor=vendor,
        total=stats["total"],
        match_count=stats["match_count"],
        unknown_count=stats["unknown_count"],
        label_set=stats["label_set"],
        family_counter=stats["family_counter"],
        threat_counter=stats["threat_counter"],
        tag_counter=stats["tag_counter"],
        generic_scores=stats["generic_scores"]
    )

    return pd.DataFrame(parsed_rows), record_list, summary, error_log, _finalize_stats(stats)


def _initialize_vendor_stats() -> Dict[str, Any]:
    return {
        "total": 0,
        "parsed": 0,
        "match_count": 0,
        "unknown_count": 0,
        "label_set": set(),
        "family_counter": {},
        "threat_counter": {},
        "tag_counter": {},
        "generic_scores": [],
        "diagnostic_cases": 0
    }


def _finalize_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    stats["success_rate"] = round(stats["parsed"] / stats["total"], 4) if stats["total"] else 0.0
    return stats


def _build_error_log(vendor: str, row: Mapping[str, Any], error: str) -> Dict[str, Any]:
    return {
        "vendor": vendor,
        "sample_id": row.get("sample_id", ""),
        "label": row.get(vendor, ""),
        "error": error
    }


def _update_classification_stats(stats: Dict[str, Any], record: VendorClassificationRecord, label: str):
    stats["match_count"] += int(getattr(record, "family_match", False))
    fam = (record.family or "").strip().lower()
    stats["unknown_count"] += int(fam in {"unknown", "generic", "agent", "malware"})

    stats["label_set"].add(label)
    family = getattr(record, "family", "unknown")
    stats["family_counter"][family] = stats["family_counter"].get(family, 0) + 1

    threat = getattr(record, "malware_type", "unknown")
    stats["threat_counter"][threat] = stats["threat_counter"].get(threat, 0) + 1

    for tag in getattr(record, "threat_tags", []):
        stats["tag_counter"][tag] = stats["tag_counter"].get(tag, 0) + 1

    score = getattr(record, "signal_score", None)
    if isinstance(score, (int, float)):
        stats["generic_scores"].append(score)
