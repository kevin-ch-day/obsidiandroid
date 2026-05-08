# Filename: vendor_summary_builder.py
# Description: Builds per-sample parsed rows and per-vendor summary diagnostics for AV label classification

import math
from collections import Counter
from typing import Dict, List, Set, Union

from obsidiandroid.vendors import VendorClassificationRecord


# ---------------------------------------------------------
# Defensive Wrapper for Counter Use
# ---------------------------------------------------------
def is_counter_sanitized(obj) -> Counter:
    return obj if isinstance(obj, Counter) else Counter(obj)


# ---------------------------------------------------------
# Build Parsed Row Output
# ---------------------------------------------------------
def build_parsed_row(record: VendorClassificationRecord, true_family: str) -> Dict[str, Union[str, bool, float]]:
    has_known_family = record.is_known_family
    family_match = "Yes" if has_known_family else "No"

    if not true_family:
        family_match = "No Ground Truth"

    return {
        "sample_id": record.sample_id,
        "Original Label": record.original_label,
        "Known Family": true_family,
        "Parsed Family": record.family,
        "family": record.family,
        "Family Match": family_match,
        "Threat Class": record.threat_class,
        "Platform": record.platform,
        "Variant": record.variant,
        "Malware Type": record.malware_type,
        "Composite Tag": record.composite_tag,
        "Is Android": record.is_android,
        "Genericity Score": record.genericity_score,
    }


# ---------------------------------------------------------
# Build Summary for a Vendor
# ---------------------------------------------------------
def build_vendor_summary(
    vendor: str,
    total: int,
    match_count: int,
    unknown_count: int,
    label_set: Set[str],
    family_counter: Counter,
    threat_counter: Counter,
    tag_counter: Counter,
    generic_scores: List[float],
) -> Dict[str, Union[str, int, float, List[str], bool]]:

    # Defensive counter wrapping
    family_counter = is_counter_sanitized(family_counter)
    threat_counter = is_counter_sanitized(threat_counter)
    tag_counter = is_counter_sanitized(tag_counter)

    # Basic metrics
    match_pct = round((match_count / total) * 100.0, 2) if total else 0.0
    unknown_pct = round((unknown_count / total) * 100.0, 2) if total else 0.0
    generic_family_tokens = {"unknown", "generic", "agent", "malware"}
    generic_family_count = sum(
        count for fam, count in family_counter.items()
        if str(fam).strip().lower() in generic_family_tokens
    )
    generic_family_ratio = round(generic_family_count / total, 3) if total else 0.0
    enrichment_score = round(match_pct - unknown_pct, 2)
    avg_generic_score = round(sum(generic_scores) / len(generic_scores), 2) if generic_scores else 0.0
    normalized_entropy = _compute_normalized_entropy(family_counter)

    # Diversity metrics
    family_set = list(family_counter.keys())
    non_unknown_families = [fam for fam in family_set if fam != "unknown"]
    detection_diversity = len(non_unknown_families)
    multi_match_count = sum(1 for count in family_counter.values() if count > 1)

    # Top threat tags
    top_threats = ", ".join(f"{k}:{v}" for k, v in threat_counter.most_common(3)) if threat_counter else "none"
    top_composites = ", ".join(f"{k}:{v}" for k, v in tag_counter.most_common(3)) if tag_counter else "none"

    return {
        "Vendor": vendor,
        "Samples Evaluated": total,
        "Unique Labels": len(label_set),
        "Family Match Count": match_count,
        "Family Match Accuracy (%)": match_pct,
        "Unknown Parsed Count": unknown_count,
        "Unknown Parsed (%)": unknown_pct,
        "Detection Diversity": detection_diversity,
        "Multiple Match Labels": multi_match_count,
        "Top Threat Tags": top_threats,
        "Top Composite Tags": top_composites,
        "Enrichment Score": enrichment_score,
        "Raw Family Set": family_set,
        "Avg Genericity Score": avg_generic_score,
        "Normalized Entropy": normalized_entropy,
        "Generic Family Ratio": generic_family_ratio,
        "Has Enrichment Signal": enrichment_score > 0,
        "Is Low Accuracy": match_pct < 10.0,
        "Is Too Generic": unknown_pct > 60.0,
    }


def _compute_normalized_entropy(counter: Counter) -> float:
    """Compute normalized Shannon entropy H/log2(n)."""
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    probs = [c / total for c in counter.values() if c > 0]
    if not probs:
        return 0.0
    h = -sum(p * math.log2(p) for p in probs)
    n_unique = len(probs)
    if n_unique <= 1:
        return 0.0
    return round(h / math.log2(n_unique), 4)
