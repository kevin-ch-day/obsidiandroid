# Filename: vendor_record_selector.py
# Purpose : Select the best vendor classification record for a sample using reliability scoring

from typing import Any, List, Dict, Tuple
from model.vendor.record_core import VendorClassificationRecord
from utils import display_utils as du
from config import app_config


def select_best_vendor_record(
    sample_id: str,
    records_by_vendor: Dict[str, List[VendorClassificationRecord]],
    records_by_sample_id: Dict[str, List[VendorClassificationRecord]] | None = None,
    verbose: bool = True
) -> VendorClassificationRecord:
    """
    Selects the most reliable vendor classification record for a given sample ID.
    Preference is given to records with valid structure, known families, strong signal,
    and high confidence scores.
    """
    all_records = _gather_records_for_sample(
        sample_id,
        records_by_vendor,
        records_by_sample_id=records_by_sample_id,
        verbose=verbose,
    )

    if not all_records:
        if verbose:
            du.print_warning(
                f"[SELECTOR] No vendor records found for sample {sample_id}."
            )
        return _fallback_record(sample_id, verbose)

    try:
        ranked = sorted(all_records, key=_evaluate_record_rank, reverse=True)
        best = ranked[0]

        if not _evaluate_record_rank(best)[0] and verbose:
            du.print_warning(
                f"[SELECTOR] Selected record for {sample_id} is structurally weak."
            )

        return best
    except Exception as e:
        if verbose:
            du.print_error(
                f"[SELECTOR] Selection error for {sample_id}: {type(e).__name__} - {e}"
            )
        return _fallback_record(sample_id, verbose)


def _gather_records_for_sample(
    sample_id: str,
    records_by_vendor: Dict[str, List[VendorClassificationRecord]],
    records_by_sample_id: Dict[str, List[VendorClassificationRecord]] | None = None,
    verbose: bool = False,
) -> List[VendorClassificationRecord]:
    """
    Gathers all classification records matching a sample ID across vendors.
    """
    def _norm(val: str) -> str:
        try:
            f = float(val)
            i = int(f)
            if f == i:
                return str(i)
        except (ValueError, TypeError):
            pass
        return str(val)

    normalized = _norm(sample_id)
    if isinstance(records_by_sample_id, dict):
        return list(records_by_sample_id.get(normalized, []))

    result = []
    for vendor, recs in records_by_vendor.items():
        for r in recs:
            try:
                if _norm(getattr(r, "sample_id", "")) == normalized:
                    result.append(r)
            except Exception:
                continue
    if (
        verbose
        and getattr(app_config, "DEBUG_MODE", False)
        and result
        and isinstance(records_by_vendor, dict)
    ):
        du.print_debug(
            f"[SELECTOR] Gathered {len(result)} record(s) for sample {sample_id}"
        )
    return result


def _evaluate_record_rank(record: VendorClassificationRecord) -> Tuple[bool, bool, bool, float]:
    """
    Produces a tuple (valid, known, signal, confidence) for sorting vendor records.
    Higher values sort first in descending order.
    """
    try:
        valid = record.is_valid() if callable(record.is_valid) else record.is_valid
        known = record.is_known_family if not callable(record.is_known_family) else record.is_known_family()
        high_signal = record.is_high_signal if not callable(record.is_high_signal) else record.is_high_signal()
        confidence = float(record.confidence_score) if not callable(record.confidence_score) else float(record.confidence_score())

        return bool(valid), bool(known), bool(high_signal), confidence
    except Exception as e:
        du.print_warning(f"[SELECTOR] Failed to rank record from {record.vendor_name}: {e}")
        return False, False, False, 0.0


def _fallback_record(sample_id: str, verbose: bool = True) -> VendorClassificationRecord:
    """
    Returns a placeholder classification record when no valid data is available.
    """
    if verbose:
        du.print_warning(
            f"[SELECTOR] Generating fallback record for sample {sample_id}."
        )
    return VendorClassificationRecord(
        sample_id=sample_id,
        vendor_name="unknown",
        original_label="unknown"
    )
