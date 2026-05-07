# Filename: src/obsidiandroid/inference/threat_class_engine.py
# Description: AI-style threat class inference using trusted vendor labels, traits, and heuristics

import re
from typing import Dict, List
from collections import Counter

# ------------------------------------------------------------------
# Core Inference Function
# ------------------------------------------------------------------

def infer_threat_class(
    family: str,
    traits: List[str],
    original_label: str,
    trusted_vendor_labels: List[str] | None = None,
    debug: bool = False,
) -> str:
    """
    Infers a threat class using heuristics across multiple metadata sources.
    Returns the most likely threat class or 'generic' as fallback.
    """
    if trusted_vendor_labels is None:
        trusted_vendor_labels = []
    label = (original_label or "").lower()
    family = (family or "").lower()
    traits = [t.lower() for t in traits if t]
    vendor_labels = [vl.lower() for vl in trusted_vendor_labels if vl]

    combined = " ".join([label] + vendor_labels + traits + [family])
    candidates = {}

    # Apply match-based heuristics
    for keyword, threat_class in _keyword_map().items():
        if any(re.search(rf"\b{re.escape(keyword)}\b", src) for src in vendor_labels):
            candidates[threat_class] = candidates.get(threat_class, 0.0) + 0.9  # strong vendor match
        if threat_class in traits:
            candidates[threat_class] = candidates.get(threat_class, 0.0) + 0.8  # trait match
        if keyword in family:
            candidates[threat_class] = candidates.get(threat_class, 0.0) + 0.6  # family match
        if keyword in combined:
            candidates[threat_class] = candidates.get(threat_class, 0.0) + 0.4  # combined signal

    if not candidates:
        if debug:
            print("[DEBUG] No threat class match found. Returning 'generic'.")
        return "generic"

    # Pick the highest scoring threat class
    selected = sorted(candidates.items(), key=lambda x: -x[1])[0]
    if debug:
        print(f"[DEBUG] Selected threat_class = '{selected[0]}' (score={selected[1]:.2f})")
        for cls, score in sorted(candidates.items(), key=lambda x: -x[1]):
            print(f"         -> {cls:<12} = {score:.2f}")

    return selected[0]


# ------------------------------------------------------------------
# Keyword-to-ThreatClass Mapping
# ------------------------------------------------------------------

def _keyword_map() -> Dict[str, str]:
    """
    Maps malware-related keywords to standardized threat classes.
    """
    return {
        "bank": "banker",
        "sms": "sms-trojan",
        "spy": "spyware",
        "spynote": "spyware",
        "monitor": "monitor",
        "keylog": "keylogger",
        "drop": "dropper",
        "down": "downloader",
        "steal": "stealer",
        "locker": "locker",
        "click": "clicker",
        "ad": "adware",
        "rat": "rat",
        "inject": "injector",
        "back": "backdoor",
        "ransom": "ransomware",
        "agent": "agent",
        "bot": "botnet",
        "pup": "pup",
        "generic": "generic"
    }


# ------------------------------------------------------------------
# Optional Analysis Tool
# ------------------------------------------------------------------

def analyze_threat_class_distribution(df, verbose: bool = True):
    """
    Displays top threat class frequencies from a labeled DataFrame.
    """
    threat_counts = Counter(df['threat_class'])

    if verbose:
        print("\nTop Threat Classes:")
        for threat, count in threat_counts.most_common(10):
            print(f"{threat:<15} = {count}")

        unknowns = df[df['threat_class'].isin(['unknown', 'generic'])]
        print(f"\n[INFO] Unknown/Generic threat_class count: {len(unknowns)}")
        if not unknowns.empty:
            print(unknowns[['classification_label', 'family', 'traits']].head(10))

    return threat_counts
