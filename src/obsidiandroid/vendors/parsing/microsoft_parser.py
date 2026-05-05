# Filename: microsoft_parser.py
# Description: Parser for Microsoft-style malware classification strings, returning ParsedLabelMetadata.

from typing import Dict, Optional
from .parser_defaults import ParserDefaults
from . import parser_confidence_estimator
from obsidiandroid.vendors.contracts.parsed_label_metadata import ParsedLabelMetadata

IRRELEVANT_TYPES = {"program", "dos", "pua", "generic", "unknown"}

THREAT_KEYWORDS = {
    "dropper": "dropper",
    "spy": "spy",
    "banker": "banker",
    "backdoor": "backdoor",
    "trojan": "trojan",
    "ransom": "ransom"
}

RAT_FAMILY_HINTS = {
    "realrat", "telerat", "lodarat", "aitarat", "xrat", "gravityrat",
    "androrat", "sandrorat", "onrat", "nanocore", "dcrat", "quasarrat",
}

def _is_valid_microsoft_format(label: str) -> bool:
    return ":" in label and "/" in label

def _extract_components(label: str) -> Optional[Dict[str, str]]:
    try:
        malware_type_raw, remainder = label.split(":", 1)
        platform, signature = remainder.split("/", 1)
        return {
            "malware_type_raw": malware_type_raw.strip(),
            "platform": platform.strip(),
            "signature": signature.strip()
        }
    except Exception:
        return None

def _normalize_malware_type(malware_type_raw: str) -> str:
    lowered = malware_type_raw.lower()
    return "Other" if lowered in IRRELEVANT_TYPES else malware_type_raw.capitalize()

def _extract_family_token(signature: str, platform: str) -> tuple[str, str]:
    try:
        candidate = signature.split("!")[0].split(".")[0].strip().lower()
        if not candidate or candidate == platform.lower():
            return "unknown", "redundant_family_platform"
        return candidate, "structured"
    except Exception:
        return "unknown", "family_extraction_error"

def _infer_threat_class(malware_type: Optional[str]) -> str:
    if not malware_type or not isinstance(malware_type, str):
        return "unknown"
    lowered = malware_type.strip().lower()
    for keyword, tag in THREAT_KEYWORDS.items():
        if keyword in lowered:
            return tag
    return "unknown"

def parse_microsoft_classification(classification: str, engine_metadata: Optional[Dict] = None) -> ParsedLabelMetadata:
    result = ParserDefaults.eight_field_fallback()
    result["edge_case_type"] = "none"

    if not classification or not isinstance(classification, str):
        result["edge_case_type"] = "invalid_or_empty"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))

    classification = classification.strip()
    if not _is_valid_microsoft_format(classification):
        result["edge_case_type"] = "bad_format"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))

    components = _extract_components(classification)
    if not components:
        result["edge_case_type"] = "split_failure"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))

    malware_type = _normalize_malware_type(components["malware_type_raw"])
    platform = components["platform"].capitalize()
    signature = components["signature"]
    family, edge_case_type = _extract_family_token(signature, platform)
    threat_class = _infer_threat_class(malware_type)

    result.update({
        "malware_type": malware_type,
        "platform": platform,
        "family": family,
        "variant": signature,
        "threat_class": threat_class,
        "edge_case_type": edge_case_type,
        "parser_quality": engine_metadata.get("parser_quality", "medium") if engine_metadata else "medium",
        "signature_type": engine_metadata.get("signature_type", "pattern") if engine_metadata else "pattern"
    })

    fam_lc = str(result.get("family", "")).strip().lower()
    if fam_lc in RAT_FAMILY_HINTS:
        result["threat_class"] = "rat"
        if str(result.get("malware_type", "")).strip().lower() in {
            "trojan", "trojanspy", "backdoor", "unknown", ""
        }:
            result["malware_type"] = "rat"

    try:
        result["confidence"] = parser_confidence_estimator.compute_confidence_score(
            label=classification,
            parsed_result=result,
            metadata=engine_metadata
        )
    except Exception:
        result["confidence"] = 0.0
        result["edge_case_type"] = "confidence_calc_fail"

    return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))
