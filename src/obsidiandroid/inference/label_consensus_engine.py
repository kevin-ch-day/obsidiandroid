# Filename: src/obsidiandroid/inference/label_consensus_engine.py
# Purpose : Resolve consensus label per sample from multiple vendor records.

from collections import Counter
from typing import Any, Dict, List

from obsidiandroid.vendors import VendorClassificationRecord
from .signal_health_checker import analyze_signal_health

GENERIC_TOKENS = {"generic", "unknown", "none", "agent", "malware"}


def is_counter_sanitized(obj: Any, debug: bool = False) -> Counter:
    if isinstance(obj, Counter):
        return obj

    try:
        c = Counter(obj)
        if debug:
            print("[DEBUG] Counter successfully created from object.")
        return c
    except Exception as e:
        if debug:
            print(f"[ERROR] Failed to sanitize object into Counter: {e} — type: {type(obj)}")
        return Counter()


def most_common_non_generic(values: List[str], debug: bool = False) -> str:
    counter = Counter(
        val
        for v in values
        if isinstance(v, str)
        and (val := v.strip().lower())
        and val not in GENERIC_TOKENS
    )

    if debug:
        print("[DEBUG] Non-generic normalized values:", list(counter.elements()))
        print("[DEBUG] Counter contents:", dict(counter))

    try:
        return counter.most_common(1)[0][0] if counter else "unknown"
    except Exception as e:
        if debug:
            print(f"[ERROR] most_common() failed: {e}")
        return "unknown"


def weighted_field_choice(records: List[VendorClassificationRecord], field_name: str, debug: bool = False) -> str:
    weighted = Counter()

    if debug:
        print(f"\n[DEBUG] Starting weighted_field_choice() for field: '{field_name}'")

    for record in records:
        value = getattr(record, field_name, "") or ""
        value = value.strip().lower()

        if value and value not in GENERIC_TOKENS:
            score = getattr(record, "confidence_score", None)
            weight = score if score is not None else 0.5
            weighted[value] += weight
            if debug:
                print(f"[DEBUG] +{weight:.2f} -> '{value}'")

    if debug:
        print(f"[DEBUG] Weighted Counter for '{field_name}':", dict(weighted))

    try:
        return weighted.most_common(1)[0][0] if weighted else "unknown"
    except Exception as e:
        if debug:
            print(f"[ERROR] most_common() failed on weighted counter: {e}")
        return "unknown"


def aggregate_tags(records: List[VendorClassificationRecord], debug: bool = False) -> List[str]:
    tags = set()
    for record in records:
        tag_list = record.threat_tags or []
        tags.update(tag.strip().lower() for tag in tag_list if tag)

    if debug:
        print("[DEBUG] Aggregated threat tags:", sorted(tags))

    return sorted(tags)


def aggregate_vendor_sources(records: List[VendorClassificationRecord], debug: bool = False) -> List[str]:
    vendors = {r.vendor_name for r in records if r.vendor_name}
    if debug:
        print("[DEBUG] Vendor sources:", sorted(vendors))
    return sorted(vendors)


def resolve_consensus_label(records: List[VendorClassificationRecord], debug: bool = False) -> Dict[str, Any]:
    if debug:
        print("\n[DEBUG] resolve_consensus_label() called with", len(records), "records")

    valid_records = [r for r in records if r and r.is_valid and r.original_label]

    if debug:
        print(f"[DEBUG] Valid records after filtering: {len(valid_records)}")

    if not valid_records:
        if debug:
            print("[DEBUG] No valid records — returning default unknown label.")
        return {
            "platform": "unknown",
            "malware_type": "unknown",
            "threat_class": "unknown",
            "family": "unknown",
            "variant": "unknown",
            "confidence": 0.0,
            "tags": [],
            "vendors": []
        }

    consensus = {
        "platform": weighted_field_choice(valid_records, "platform", debug),
        "malware_type": weighted_field_choice(valid_records, "malware_type", debug),
        "threat_class": weighted_field_choice(valid_records, "threat_class", debug),
        "family": weighted_field_choice(valid_records, "family", debug),
        "variant": most_common_non_generic([r.variant for r in valid_records], debug),
        "tags": aggregate_tags(valid_records, debug),
        "vendors": aggregate_vendor_sources(valid_records, debug),
    }

    signal_stats = analyze_signal_health(valid_records)
    consensus["confidence"] = round(signal_stats.get("signal_strength", 0.0), 4)

    if debug:
        print("\n[CONSENSUS DEBUG] === Final Resolved Fields ===")
        for k, v in consensus.items():
            val_str = "; ".join(v) if isinstance(v, list) else str(v)
            print(f" - {k:<15}: {val_str}")
        print("[DEBUG] Signal health stats:", signal_stats)

    return consensus
