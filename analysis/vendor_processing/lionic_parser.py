# Filename: lionic_parser.py
# Description: Parser for Lionic AV classification labels

from typing import Dict, Optional
from .parser_defaults import ParserDefaults
from . import parser_confidence_estimator

FAMILY_ALIAS = {
    "banbra": "bankbot", "basbanke": "bankbot", "banker": "bankbot",
    "spyloan": "spynote", "callerspy": "spynote", "smsspy": "spynote", "mobok": "spynote",
    "hiddad": "adware", "hiddenad": "adware", "hiddapp": "adware", "browserad": "adware",
    "generic": "unknown"
}

def split_label(classification: str) -> list:
    return [p.strip() for p in classification.replace(":", ".").split(".") if p.strip()]

def normalize_family(family: str) -> str:
    fam = family.lower()
    for alias, standard in FAMILY_ALIAS.items():
        if alias in fam:
            return standard
    return fam

def infer_threat_class(family: str) -> str:
    fam = family.lower()
    if "rat" in fam or "remote" in fam:
        return "rat"
    if "bank" in fam:
        return "banker"
    if "spy" in fam:
        return "spy"
    if "drop" in fam:
        return "dropper"
    if "ransom" in fam or "locker" in fam:
        return "ransom"
    if "fake" in fam or "spoof" in fam:
        return "spoof"
    if any(ad in fam for ad in ["adware", "hiddenad", "browserad"]):
        return "adware"
    if "riskware" in fam:
        return "riskware"
    if "hacktool" in fam or "metasploit" in fam:
        return "hacktool"
    if "worm" in fam:
        return "worm"
    return "trojan"

def get_part(parts: list, index: int, default: str) -> str:
    return parts[index] if len(parts) > index else default

def parse_lionic_classification(classification: str, metadata: Optional[Dict] = None) -> Dict[str, str]:
    result = ParserDefaults.eight_field_fallback()

    if not classification or not isinstance(classification, str):
        return result

    try:
        parts = split_label(classification)

        result["malware_type"] = get_part(parts, 0, "Other")
        result["platform"] = get_part(parts, 1, "AndroidOS")

        raw_family = get_part(parts, 2, "unknown")
        result["family"] = normalize_family(raw_family)
        result["variant"] = get_part(parts, 3, "unknown")

        result["threat_class"] = infer_threat_class(result["family"])

        # Automatically compute confidence score based on structure and metadata
        result["confidence"] = parser_confidence_estimator.compute_confidence_score(
            label=classification,
            parsed_result=result,
            metadata=metadata
        )

        result["parser_quality"] = metadata.get("parser_quality", "pattern") if metadata else "pattern"
        result["signature_type"] = metadata.get("signature_type", "pattern") if metadata else "pattern"

    except Exception:
        return ParserDefaults.eight_field_fallback()

    return ParserDefaults.normalize(result)
