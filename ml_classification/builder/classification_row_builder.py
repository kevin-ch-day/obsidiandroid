# Filename: classification_row_builder.py
# Purpose  : Build structured classification output rows from selected vendor records and model predictions

from typing import Dict, Any, Optional
from model.vendor.record_core import VendorClassificationRecord
from ml_classification.labeling.label_format_generator import generate_label
from ml_classification.labeling import label_field_normalizer
from utils import display_utils as du
from . import vendor_record_selector
from . import record_enrichment
from . import prediction_utils
from . import classification_constants as const
from ml_classification.common.malware_family_constants import is_known_family_name


def _normalize_family_id_token(value: Any) -> str:
    """Normalize family-id-like values into stable string keys."""
    try:
        fval = float(value)
        ival = int(fval)
        if fval == ival:
            return str(ival)
    except Exception:
        pass
    return str(value).strip()


def _build_canonical_category_vector(
    predicted_family: str,
    normalized_fields: Dict[str, Any],
    record: VendorClassificationRecord,
) -> str:
    """Build a stable category vector aligned with final normalized output."""
    platform = normalized_fields.get("platform") or record.platform or "android"
    threat = normalized_fields.get("threat") or record.threat_class or "generic"
    malware_type = normalized_fields.get("mtype") or record.malware_type or "trojan"
    vector = [
        f"platform:{platform}",
        f"family:{predicted_family}",
        f"threat:{threat}",
        f"type:{malware_type}",
    ]
    if normalized_fields.get("variant"):
        vector.append("has_variant")
    if bool(normalized_fields.get("is_known_family")):
        vector.append("known_family")
    return ";".join(vector)


def build_classification_row(
    sample_id: str,
    pred_index: int,
    label_decoder: Dict[int, str],
    true_labels: Dict[str, str],
    metadata: Dict[str, Any],
    label_name_map: Optional[Dict[str, str]] = None,
    records_by_vendor: Optional[Dict[str, Any]] = None,
    records_by_sample_id: Optional[Dict[str, Any]] = None,
    label_format: str = "structured",
    include_confidence: bool = True,
    debug: bool = False,
    consensus_data: Optional[Dict[str, Any]] = None
) -> dict:
    """
    Constructs a structured classification row for a malware sample based on ML prediction
    and AV vendor metadata.
    """
    # Backward compatibility: older callers passed `records_by_vendor`
    # as the 6th positional argument where `label_name_map` now lives.
    if records_by_vendor is None and isinstance(label_name_map, dict):
        if any(isinstance(v, list) for v in label_name_map.values()):
            records_by_vendor = label_name_map
            label_name_map = {}

    if label_name_map is None:
        label_name_map = {}
    if records_by_vendor is None:
        records_by_vendor = {}
    if records_by_sample_id is None:
        records_by_sample_id = {}

    predicted_family_id = prediction_utils.decode_prediction(pred_index, label_decoder)
    true_family_id = true_labels.get(sample_id, "unknown")
    predicted_family = label_name_map.get(str(predicted_family_id), predicted_family_id)
    true_family = label_name_map.get(str(true_family_id), true_family_id)

    selected_record = vendor_record_selector.select_best_vendor_record(
        sample_id,
        records_by_vendor,
        records_by_sample_id=records_by_sample_id,
        verbose=debug,
    )

    enriched_variant = record_enrichment.enrich_variant_from_trusted_vendors(
        sample_id,
        records_by_vendor,
        selected_record.variant,
        records_by_sample_id=records_by_sample_id,
    )
    if isinstance(enriched_variant, tuple) and enriched_variant:
        selected_record.variant = enriched_variant[0]
    else:
        selected_record.variant = enriched_variant

    enriched_threat = record_enrichment.enrich_threat_class_if_unknown(
        selected_record, debug=debug
    )
    if isinstance(enriched_threat, tuple) and enriched_threat:
        selected_record.threat_class = enriched_threat[0]
    else:
        selected_record.threat_class = enriched_threat

    if consensus_data:
        threat_val = consensus_data.get("threat_class")
        if (
            isinstance(threat_val, str)
            and threat_val
            and threat_val.lower() != "unknown"
        ):
            selected_record.threat_class = threat_val

        type_val = consensus_data.get("malware_type")
        if (
            isinstance(type_val, str)
            and type_val
            and type_val.lower() != "unknown"
        ):
            selected_record.malware_type = type_val

    normalized_fields: Dict[str, Any] = {}
    # Normalize record fields before generating output label to keep
    # classification_label semantically aligned with emitted columns.
    try:
        normalized_fields = label_field_normalizer.generate_structured_fields(
            recorded_family=predicted_family,
            record=selected_record,
            debug=False,
        )
        selected_record.platform = (
            normalized_fields.get("platform") or selected_record.platform
        )
        selected_record.malware_type = (
            normalized_fields.get("mtype") or selected_record.malware_type
        )
        selected_record.threat_class = (
            normalized_fields.get("threat") or selected_record.threat_class
        )
    except Exception:
        normalized_fields = {}

    classification_label = generate_label(
        recorded_family=predicted_family,
        record=selected_record,
        format=label_format,
        verbose=debug
    )

    setattr(selected_record, "_predicted_family_fallback", predicted_family)
    label_validity = prediction_utils.check_label_completeness(
        selected_record, sample_id, verbose=debug
    )

    traits = normalize_trait_tags(selected_record.threat_tags)
    categories = _build_canonical_category_vector(
        predicted_family=predicted_family,
        normalized_fields=normalized_fields,
        record=selected_record,
    )
    confidence = prediction_utils.get_sample_confidence(metadata, sample_id, include_confidence)

    high_confidence = False
    try:
        high_confidence_attr = selected_record.is_high_signal
        high_confidence = high_confidence_attr() if callable(high_confidence_attr) else bool(high_confidence_attr)
    except Exception as e:
        if debug:
            du.print_warning(f"[WARN] Cannot evaluate high_confidence for {sample_id}: {type(e).__name__} - {e}")

    return _build_output_row(
        sample_id=sample_id,
        true_family=true_family,
        predicted_family=predicted_family,
        label=classification_label,
        record=selected_record,
        traits=traits,
        categories=categories,
        confidence=confidence,
        high_confidence=high_confidence,
        label_validity=label_validity,
        variant=selected_record.variant,
        true_family_id=_normalize_family_id_token(true_family_id),
        predicted_family_id=_normalize_family_id_token(predicted_family_id),
    )


def normalize_trait_tags(tags: Optional[list]) -> str:
    """
    Normalize and alias malware traits using constants.
    """
    if not tags:
        return ""

    normalized_tags = set()
    for tag in tags:
        if isinstance(tag, str) and tag.strip():
            clean_tag = tag.strip().lower()
            alias_tag = const.TRAIT_TAG_ALIASES.get(clean_tag, clean_tag)
            normalized_tags.add(alias_tag)

    return ";".join(sorted(normalized_tags))


def _build_output_row(
    sample_id: str,
    true_family: str,
    predicted_family: str,
    label: str,
    record: VendorClassificationRecord,
    traits: str,
    categories: str,
    confidence: float,
    label_validity,
    variant: str,
    high_confidence: bool,
    true_family_id: str,
    predicted_family_id: str,
) -> dict:
    """
    Constructs a dictionary with all relevant classification data for downstream analysis.
    """
    known_family = bool(getattr(record, "is_known_family", False)) or is_known_family_name(predicted_family)
    output_row = {
        "sample_id": sample_id,
        "true_family": true_family,
        "predicted_family": predicted_family,
        "classification_label": label,
        "platform": record.platform or "android",
        "malware_type": record.malware_type or "trojan",
        "threat_class": record.threat_class or "generic",
        "variant": variant,
        "traits": traits,
        "composite_tag": record.composite_tag or "",
        "category_vector": categories,
        "known_family": known_family,
        "genericity_score": round(record.genericity_score or 0.0, 4),
        "label_validity": label_validity,
        "signal_score": record.signal_score,
        "high_confidence": high_confidence,
        "confidence": round(float(confidence), 4) if confidence is not None else None,
        "true_family_id": true_family_id,
        "predicted_family_id": predicted_family_id,
    }

    return output_row
