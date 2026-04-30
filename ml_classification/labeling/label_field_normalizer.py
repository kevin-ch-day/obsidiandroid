# Filename: ml_classification/label_field_normalizer.py
# Purpose  : Structured normalization and data engineering logic for AV label diagnostics and classification enrichment

import re
from model.vendor.record_core import VendorClassificationRecord
from ml_classification.inference.threat_class_engine import infer_threat_class
from ml_classification.inference.malware_type_engine import infer_malware_type
from ml_classification.common.malware_family_constants import (
    GENERIC_TOKENS,
    is_known_family_name,
    normalize_family_name,
)

# Default fallback values
DEFAULT_PLATFORM = "android"
DEFAULT_TYPE = "trojan"
DEFAULT_THREAT = "generic"
DEFAULT_FAMILY = "unknown"

THREAT_CLASS_ALIASES = {
    "remote access trojan": "rat",
    "remote-access trojan": "rat",
    "remote_access_trojan": "rat",
    "remote access": "rat",
    "remote-access": "rat",
    "remote_access": "rat",
    "remote administration tool": "rat",
    "remote-admin": "rat",
}

MALWARE_TYPE_ALIASES = {
    "sms trojan": "sms-trojan",
    "remote access trojan": "rat",
    "remote-access trojan": "rat",
    "remote administration tool": "rat",
}


def _normalize_text_field(value: str, default: str = DEFAULT_FAMILY) -> str:
    """Clean and normalize basic text fields like family, type, threat, etc."""
    token = re.sub(r"\s+", " ", str(value or "").strip().lower())
    fallback = re.sub(r"\s+", " ", str(default or "").strip().lower())
    if token in {"", "unknown"}:
        return fallback
    return token


def _canonicalize_threat_class(value: str) -> str:
    """Map noisy threat class phrases to canonical tokens."""
    token = _normalize_text_field(value, default=DEFAULT_THREAT)
    if not token:
        return DEFAULT_THREAT
    token = THREAT_CLASS_ALIASES.get(token, token)
    token = token.replace("_", "-").strip()
    return token or DEFAULT_THREAT


def _canonicalize_malware_type(value: str) -> str:
    """Map noisy malware type phrases to canonical type labels."""
    token = _normalize_text_field(value, default=DEFAULT_TYPE)
    if not token:
        return DEFAULT_TYPE
    token = MALWARE_TYPE_ALIASES.get(token, token)
    token = token.replace("_", "-").strip()
    return token or DEFAULT_TYPE


def _normalize_variant_field(value: str) -> str:
    """Sanitize and filter variant values."""
    variant = (value or "").strip().lower()
    if variant == "unknown" or variant.isdigit() or len(variant) == 1:
        return ""
    return variant


def _deduplicate_fields(threat: str, mtype: str) -> tuple[str, str]:
    """Clean up threat/type values to prevent redundancy or invalid combinations."""
    threat = (threat or "").strip().lower()
    mtype = (mtype or "").strip().lower()

    if mtype == "malware":
        if threat and threat not in GENERIC_TOKENS:
            return threat, threat
        return threat, "malware"

    if not mtype or mtype == "unknown":
        return threat, ""

    if not re.search(r"[a-z]", mtype):
        return threat, DEFAULT_TYPE

    if threat in {"rat", "remote-access"} and mtype in {"trojan", "malware", "generic"}:
        return threat, "rat"

    return threat, mtype


def _infer_platform(record: VendorClassificationRecord) -> str:
    """Guess platform based on label content if not explicitly set."""
    if record.platform:
        return _normalize_text_field(record.platform, default=DEFAULT_PLATFORM)
    elif "android" in (record.original_label or "").lower():
        return "android"
    return DEFAULT_PLATFORM


def compute_record_quality(fields: dict) -> str:
    """Assign a quality score based on presence of generic or missing fields."""
    generic_fields = sum(f in {"", "unknown", "generic"} for f in [
        fields.get("family", ""), fields.get("threat", ""),
        fields.get("mtype", ""), fields.get("variant", "")
    ])
    if generic_fields >= 3:
        return "low"
    elif generic_fields == 2:
        return "medium"
    return "high"


def generate_structured_fields(
    recorded_family: str,
    record: VendorClassificationRecord,
    debug: bool = False
) -> dict:
    """
    Construct normalized and enriched field dictionary from a vendor classification record.
    """
    family = _normalize_text_field(recorded_family or record.family)
    family = normalize_family_name(family)

    try:
        inferred_threat = infer_threat_class(
            family=family,
            traits=record.threat_tags or [],
            original_label=record.original_label,
            trusted_vendor_labels=(record.category_vector or []) + [record.vendor_name, record.original_label],
            debug=debug
        )
    except Exception:
        inferred_threat = DEFAULT_THREAT

    try:
        inferred_type = infer_malware_type(
            family=family,
            tags=(record.threat_tags or []) + [record.threat_class],
            vendor_hints=(record.category_vector or []) + [record.original_label, record.vendor_name],
            debug=debug
        )
    except Exception:
        inferred_type = DEFAULT_TYPE

    # Normalize all primary fields
    threat = _canonicalize_threat_class(record.threat_class or inferred_threat)
    mtype = _canonicalize_malware_type(record.malware_type or inferred_type)
    platform = _infer_platform(record)
    variant = _normalize_variant_field(record.variant)

    # Refine threat and type to avoid redundancy
    threat, mtype = _deduplicate_fields(threat, mtype)

    # Filter out generic values from tags/vectors
    tags = sorted(set(t for t in (record.threat_tags or []) if t not in GENERIC_TOKENS))
    vector = sorted(set(v for v in (record.category_vector or []) if v not in GENERIC_TOKENS))

    # Extract fallback metadata
    parser_confidence = round(getattr(record, "parser_confidence", 0.0) or 0.0, 4)
    parser_source = getattr(record, "parser_source", record.vendor_name or "unknown")
    is_known = bool(record.is_known_family) or is_known_family_name(family)

    enriched = {
        "family": family,
        "threat": threat,
        "mtype": mtype,
        "platform": platform,
        "variant": variant,
        "tags": tags,
        "vector": vector,
        "is_known_family": is_known,
        "is_generic_family": record.is_generic_family,
        "confidence": round(record.confidence_score or 0.0, 4),
        "genericity_score": round(record.genericity_score or 0.0, 4),
        "parser_confidence": parser_confidence,
        "parser_source": parser_source,
        "record_quality": compute_record_quality({
            "family": family, "threat": threat, "mtype": mtype, "variant": variant
        })
    }

    if debug:
        log_structured_field_debug(enriched, record)

    return enriched


def log_structured_field_debug(fields: dict, record: VendorClassificationRecord):
    """Print a debug summary of the normalized field structure."""
    print("\n[LABEL DEBUG] === Structured Field Analysis ===")
    for k, v in fields.items():
        value_str = ";".join(v) if isinstance(v, list) else v
        print(f" - {k:<18}: {value_str}")
    print("[LABEL DEBUG] --- Source Record ---")
    print(record.verbose_summary())
    print("[LABEL DEBUG] ----------------------\n")


def inspect_record_label_inference(record: VendorClassificationRecord, recorded_family: str = "") -> dict:
    """Debug helper for inspecting classification field inference."""
    print(f"\n[INSPECTOR] Evaluating Sample: {record.sample_id} | Vendor: {record.vendor_name}")
    return generate_structured_fields(recorded_family, record, debug=True)
