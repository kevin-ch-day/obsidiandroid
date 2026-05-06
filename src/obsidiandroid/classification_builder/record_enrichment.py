# Filename: record_enrichment.py
# Purpose : Smart enrichment of 'variant' and 'threat_class' fields using trusted vendor data and inference models

from typing import Any, Dict, List, Optional, Tuple
from obsidiandroid.vendors.contracts.record_core import VendorClassificationRecord
from . import classification_constants
from obsidiandroid.inference.threat_class_engine import infer_threat_class
from obsidiandroid.cli.ui import display as du
import difflib


def enrich_variant_from_trusted_vendors(
    sample_id: str,
    records_by_vendor: Dict[str, List[VendorClassificationRecord]],
    current_variant: Optional[str],
    records_by_sample_id: Optional[Dict[str, List[VendorClassificationRecord]]] = None,
    debug: bool = False
) -> Tuple[str, float, str, List[str]]:
    """
    Enriches the 'variant' field by scanning trusted vendors and ranking candidates using AI-style scoring.
    Returns enriched variant, confidence score, selected vendor, and explanation path.
    """
    variant_input = (current_variant or "").strip().lower()
    if variant_input and variant_input != "unknown":
        return current_variant, 1.0, "original", ["source=original", "confidence=1.0"]

    candidates = []

    trusted_vendor_keys = {
        str(vendor).strip().lower()
        for vendor in classification_constants.TRUSTED_VARIANT_ENGINES
    }
    candidate_records: List[VendorClassificationRecord]
    normalized_sample_id = _normalize_sample_id(sample_id)
    if isinstance(records_by_sample_id, dict):
        candidate_records = list(records_by_sample_id.get(normalized_sample_id, []))
    else:
        candidate_records = []
        for vendor_name, rec_list in records_by_vendor.items():
            if str(vendor_name).strip().lower() in trusted_vendor_keys:
                candidate_records.extend(rec_list)

    for rec in candidate_records:
        if _normalize_sample_id(getattr(rec, "sample_id", "")) != normalized_sample_id:
            continue
        vendor_name = str(getattr(rec, "vendor_name", "")).strip().lower()
        if vendor_name not in trusted_vendor_keys:
            continue

        candidate = (rec.variant or "").strip().lower()
        if not candidate or candidate == "unknown":
            continue

        score, details = _score_variant_quality(rec)
        candidates.append((candidate, score, vendor_name, details))

    if not candidates:
        return "unknown", 0.0, "none", ["reason=no_candidates"]

    # Sort by composite score
    best_variant, best_score, best_vendor, best_explanation = sorted(candidates, key=lambda x: -x[1])[0]

    if debug:
        du.print_debug(f"[AI-ENRICH] Variant '{best_variant}' for {sample_id} (vendor={best_vendor}, score={best_score:.2f})")
        for note in best_explanation:
            du.print_debug(f"           └─ {note}")

    return best_variant, best_score, best_vendor, best_explanation


def enrich_threat_class_if_unknown(
    record: VendorClassificationRecord,
    debug: bool = False
) -> Tuple[str, float, str, List[str]]:
    """
    Uses AI-style inference to enrich the 'threat_class' field with traceable reasoning.
    Returns inferred class, confidence score, source, and explanation.
    """
    current = (record.threat_class or "").strip().lower()
    if current and current != "unknown":
        return record.threat_class, 1.0, "original", ["source=original", "confidence=1.0"]

    inferred, source, confidence = _smart_infer_threat_class(record)

    explanation = [f"source={source}", f"confidence={confidence:.2f}"]
    if debug:
        du.print_info(f"[AI-INFER] Threat class: '{inferred}' for {record.sample_id}")
        for line in explanation:
            du.print_info(f"           └─ {line}")

    return inferred if inferred != "generic" else "unknown", confidence, source, explanation


# ------------------------------------------
# INTERNAL: Composite Variant Scoring
# ------------------------------------------
def _score_variant_quality(record: VendorClassificationRecord) -> Tuple[float, List[str]]:
    """
    Scores the quality of a variant using weighted AI-style heuristics.
    """
    score = 0.0
    reasons = []

    if record.parser_quality:
        quality_map = {"high": 1.0, "medium": 0.5, "low": 0.0, "unknown": 0.0}
        quality_value = quality_map.get(str(record.parser_quality).lower(), 0.0)
        score += min(quality_value * 0.4, 0.4)
        reasons.append(f"parser_quality={quality_value:.2f}")

    if getattr(record, "confidence_score", 0):
        score += min(record.confidence_score * 0.3, 0.3)
        reasons.append(f"confidence_score={record.confidence_score:.2f}")

    if record.variant and record.variant.lower() not in ["", "unknown"]:
        score += 0.15
        reasons.append("valid_variant=True")

    if (
        record.family
        and record.variant
        and record.family.lower() not in ["", "unknown"]
        and record.variant.lower() not in ["", "unknown"]
    ):
        sim = difflib.SequenceMatcher(None, record.family.lower(), record.variant.lower()).ratio()
        score += min(sim * 0.15, 0.15)
        reasons.append(f"family_variant_similarity={sim:.2f}")

    return min(score, 1.0), reasons


def _normalize_sample_id(value: Any) -> str:
    """Normalize sample IDs to stable string keys."""
    try:
        fval = float(value)
        ival = int(fval)
        if fval == ival:
            return str(ival)
    except (ValueError, TypeError):
        pass
    return str(value)


# ------------------------------------------
# INTERNAL: Smart Threat Class AI Inference
# ------------------------------------------
def _smart_infer_threat_class(record: VendorClassificationRecord) -> Tuple[str, str, float]:
    """
    Delegates to inference engine with layered AI reasoning.
    """
    result = infer_threat_class(
        family=record.family,
        traits=record.threat_tags or [],
        original_label=record.original_label,
        trusted_vendor_labels=record.category_vector or [],
        debug=False
    )

    if result == "generic":
        return "unknown", "fallback", 0.50
    elif result in record.threat_tags:
        return result, "tag_match", 0.95
    elif result in record.original_label.lower():
        return result, "label_match", 0.85
    elif result in record.family.lower():
        return result, "family_match", 0.80
    else:
        return result, "ml_infer", 0.70
