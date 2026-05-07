# Filename: src/obsidiandroid/vendors/contracts/feature_engine.py
# Purpose : Computes derived features for VendorClassificationRecord

from typing import List

def compute_all_features(record) -> None:
    """
    Compute all derived fields on a VendorClassificationRecord instance.
    This function mutates the object in-place.
    """
    # Platform check
    platform_str = str(record.platform or "").strip().lower()
    record.is_android = platform_str == "android"

    # Validity check for classification fields
    core_fields = [record.family, record.malware_type, record.threat_class]
    normalized = [str(f or "").strip().lower() for f in core_fields]
    record.is_valid = any(f not in {"", "unknown"} for f in normalized)

    # Composite tag
    record.composite_tag = build_composite_tag(record.family, record.threat_class)

    # Category vector
    record.category_vector = build_category_vector(record)

    # Threat tags
    record.threat_tags = extract_threat_tags(
        record.original_label,
        record.malware_type,
        record.threat_class
    )

    # Signal score and classification strength
    record.signal_score = record.compute_signal_score()
    record.high_signal = record.is_high_signal()

def build_composite_tag(family: str, threat_class: str) -> str:
    family = str(family or "").strip().lower()
    threat = str(threat_class or "").strip().lower()
    if family and family != "unknown" and threat and threat != "unknown":
        return f"{family}_{threat}"
    if family and family != "unknown":
        return family
    if threat and threat != "unknown":
        return threat
    return "unknown_combined"

def build_category_vector(record) -> List[str]:
    tags = []

    family = str(record.family or "").strip().lower()
    threat = str(record.threat_class or "").strip().lower()
    mtype = str(record.malware_type or "").strip().lower()
    variant = str(record.variant or "").strip().lower()

    if record.is_android:
        tags.append("platform:android")
    if family and family != "unknown":
        tags.append(f"family:{family}")
    if threat and threat != "unknown":
        tags.append(f"threat:{threat}")
    if mtype and mtype != "unknown":
        tags.append(f"type:{mtype}")
    if variant and variant != "unknown":
        tags.append("has_variant")
    if record.is_known_family:
        tags.append("known_family")
    if record.is_generic_family:
        tags.append("generic_family")

    return tags

def extract_threat_tags(label: str, malware_type: str, threat_class: str) -> List[str]:
    keywords = [
        "banker", "rat", "sms", "clicker", "spy", "dropper", "locker",
        "adware", "ransom", "injector", "stealer", "downloader", "spynote", "keylogger"
    ]
    try:
        fields = f"{label} {malware_type} {threat_class}".lower()
    except Exception:
        fields = ""
    return sorted({tag for tag in keywords if tag in fields})
