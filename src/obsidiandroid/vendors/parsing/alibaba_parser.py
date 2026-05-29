# Filename: alibaba_parser.py
# Description: Parser for Alibaba AV classification labels with dynamic confidence scoring

from typing import Dict, Optional
from .parser_defaults import ParserDefaults
from . import parser_confidence_estimator
from obsidiandroid.vendors.contracts.parsed_label_metadata import ParsedLabelMetadata

# Known families for normalization
KNOWN_FAMILIES = {
    "anubis", "cerberus", "sova", "flubot", "joker", "teabot", "marcher", "vultur",
    "spymax", "donot", "medusa", "sharkbot", "clast82", "hqwar", "trickmo", "golddigger",
    "otpstealer"
}

# Ability mapping from label prefix to malware type and threat class
ABILITY_MAP = {
    "TrojanBanker": ("Trojan", "Banker"),
    "TrojanSpy": ("Trojan", "Spy"),
    "TrojanDropper": ("Trojan", "Dropper"),
    "TrojanDownloader": ("Trojan", "Downloader"),
    "Trojan": ("Trojan", "Unknown"),
    "Backdoor": ("Backdoor", "Backdoor"),
    "Ransom": ("Ransom", "Ransom")
}

def _split_label(classification: str) -> tuple[str, str]:
    if ":" in classification:
        return classification.split(":", 1)
    return "Unknown", classification

def _extract_structure_fields(rest: str) -> tuple[str, str, str]:
    platform = "unknown"
    family = "unknown"
    variant = ""

    if "/" in rest:
        parts = rest.split(".")
        if "/" in parts[0]:
            platform, family = parts[0].split("/", 1)
        else:
            family = parts[0]

        if len(parts) > 1:
            variant = ".".join(parts[1:])

    return platform.strip(), family.strip().lower(), variant.strip().lower()

def _normalize_family_name(family: str) -> str:
    return family.title() if family.lower() in KNOWN_FAMILIES else family.lower()

def _resolve_type_and_class(prefix: str) -> tuple[str, str]:
    for key, (malware_type, threat_class) in ABILITY_MAP.items():
        if prefix.startswith(key):
            return malware_type, threat_class
    return prefix.strip(), "Unknown"

def parse_alibaba_classification(classification: str, engine_metadata: Optional[Dict] = None) -> ParsedLabelMetadata:
    result = ParserDefaults.eight_field_fallback()

    if not classification or not isinstance(classification, str):
        result["edge_case_type"] = "empty_or_invalid"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))

    try:
        classification = classification.strip()
        prefix, rest = _split_label(classification)
        malware_type, threat_class = _resolve_type_and_class(prefix)

        platform, family_raw, variant = _extract_structure_fields(rest)
        family = _normalize_family_name(family_raw)

        result.update({
            "malware_type": malware_type,
            "threat_class": threat_class,
            "platform": platform.capitalize() if platform else "Unknown",
            "family": family,
            "variant": variant,
            "parser_quality": engine_metadata.get("parser_quality", "medium") if engine_metadata else "medium",
            "signature_type": engine_metadata.get("signature_type", "pattern") if engine_metadata else "pattern"
        })

        result["confidence"] = parser_confidence_estimator.compute_confidence_score(
            label=classification,
            parsed_result=result,
            metadata=engine_metadata
        )

    except Exception:
        result = ParserDefaults.eight_field_fallback()
        result["edge_case_type"] = "exception_thrown"

    return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))
