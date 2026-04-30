# Filename: avast_parser.py
# Description: Structured and resilient parser for Avast AV classification labels with edge case handling

import re
from typing import Dict, Optional
from .parser_defaults import ParserDefaults
from . import parser_confidence_estimator

GENERIC_FAMILIES = {
    "evo-gen", "repmalware", "malware-gen", "banker",
    "agent", "dropper", "generic", "malware"
}

# Avast suffix tag → normalized threat class
AVAST_THREAT_MAP = {
    "trj": "trojan",
    "drp": "dropper",
    "spy": "spy",
    "bank": "banker",
    "mal": "malware",
    "rat": "rat",
    "pup": "pup",
    "adw": "adware",
    "scam": "scam",
    "lock": "locker"
}

KEYWORD_THREAT_HINTS = {
    "rat": "rat",
    "bank": "banker",
    "spy": "spy",
    "drop": "dropper",
    "ransom": "ransomware",
    "adw": "adware",
    "adware": "adware",
    "sms": "sms-trojan",
}

RAT_FAMILY_HINTS = {
    "realrat", "telerat", "lodarat", "aitarat", "xrat", "gravityrat",
    "androrat", "sandrorat", "onrat", "nanocore", "dcrat", "quasarrat",
}

def extract_threat_tag(label: str) -> str:
    match = re.search(r"\[(.*?)\]", label)
    if match:
        tag = match.group(1).strip().lower()
        if not tag or not tag.isalnum():
            return "unknown"
        return AVAST_THREAT_MAP.get(tag[:3], "unknown")
    return "unknown"


def infer_threat_from_label_text(label: str) -> str:
    token = (label or "").strip().lower()
    for key, value in KEYWORD_THREAT_HINTS.items():
        if key in token:
            return value
    return "unknown"

def parse_label_parts(label: str) -> Dict[str, str]:
    label_clean = re.sub(r"\s*\[.*?\]", "", label)  # Remove [tag] suffix
    result = {
        "platform": "unknown",
        "family": "unknown",
        "variant": "unknown"
    }

    match = re.match(r"(?P<platform>Android|Other|APK|Java|ELF|JS):(?P<family>[A-Za-z0-9]+)(?:[-_](?P<variant>[A-Za-z0-9]+))?", label_clean, re.IGNORECASE)
    if match:
        result["platform"] = match.group("platform").lower()
        raw_family = match.group("family").strip().lower()
        result["variant"] = match.group("variant") or "unknown"
        result["family"] = "unknown" if raw_family in GENERIC_FAMILIES else raw_family

    return result

def parse_avast_label(label: Optional[str], engine_metadata: Optional[Dict] = None) -> Dict[str, str]:
    result = ParserDefaults.eight_field_fallback()

    if not label or not isinstance(label, str):
        return result

    try:
        label = label.strip()
        threat_class = extract_threat_tag(label)
        parts = parse_label_parts(label)
        if threat_class == "unknown":
            threat_class = infer_threat_from_label_text(label)

        result.update({
            "threat_class": threat_class,
            "platform": parts["platform"],
            "family": parts["family"],
            "variant": parts["variant"],
            "malware_type": "malware",
            "confidence": parser_confidence_estimator.compute_confidence_score(
                label=label,
                parsed_result=parts,
                metadata=engine_metadata
            ),
            "parser_quality": engine_metadata.get("parser_quality", "medium") if engine_metadata else "medium",
            "signature_type": engine_metadata.get("signature_type", "pattern") if engine_metadata else "pattern"
        })

        fam_lc = str(result.get("family", "")).strip().lower()
        if fam_lc in RAT_FAMILY_HINTS:
            result["threat_class"] = "rat"
            if str(result.get("malware_type", "")).strip().lower() in {"malware", "trojan", "unknown", ""}:
                result["malware_type"] = "rat"

    except Exception:
        return ParserDefaults.eight_field_fallback()

    return ParserDefaults.normalize(result)
