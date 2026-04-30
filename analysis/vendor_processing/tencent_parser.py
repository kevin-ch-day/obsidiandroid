# Filename: tencent_parser.py
# Description: Structured parser for Tencent AV classification labels with enhanced rule handling

import re
from typing import Dict, Optional
from .parser_defaults import ParserDefaults
from . import parser_confidence_estimator
from model.parsing.parsed_label_metadata import ParsedLabelMetadata

# Known malware indicators and Android banker families
CORE_KEYWORDS = {"trojan", "backdoor", "dropper", "spy", "worm"}
KNOWN_FAMILIES = {
    "anubis", "eventbot", "godfather", "sova", "sharkbot", "flubot",
    "chameleon", "brunhilda", "spyahmyth", "anatsa", "nebula", "polph",
    "boogr", "hqwar", "nloader", "coper", "bankbot", "ermac", "teabot",
    "blackrock", "cerberus", "trickmo", "tgtoxic", "copybara", "monokle",
    "marcher", "vultur", "joker", "xenomorph", "zanubis", "irata", "gigabud",
    "spyloan", "sonicspy"
}

FAMILY_ALIAS = {
    "tgtoxic": "tgtoxic",
    "trickmo": "trickmo",
    "copybara": "copybara",
    "monokle": "monokle",
    "spyloan": "spyloan",
    "sonicspy": "sonicspy",
    "spiderbank": "unknown",
}

def normalize_label(label: str) -> str:
    return label.strip().replace("_", ".").replace("-", ".").lower()

def extract_from_structured_parts(parts: list) -> Dict[str, str]:
    result = {
        "malware_type": "unknown",
        "threat_class": "unknown",
        "family": "unknown",
        "variant": "unknown"
    }

    for i, part in enumerate(parts):
        if part in CORE_KEYWORDS:
            result["malware_type"] = part.capitalize()
            if i + 1 < len(parts):
                result["threat_class"] = parts[i + 1].capitalize()
            if i + 2 < len(parts):
                candidate = parts[i + 2]
                if candidate not in {"agent", "generic"}:
                    result["family"] = candidate
            if i + 3 < len(parts):
                result["variant"] = parts[i + 3]
            break

    return result

def detect_family_from_fallback(normalized: str) -> str:
    for fam in KNOWN_FAMILIES:
        if fam in normalized:
            return fam
    return "unknown"


def _extract_privacy_family_token(normalized: str) -> str:
    """
    Extract candidate family from Tencent privacy labels like:
      - a.privacy.BankTrickMo
      - a.privacy.SpyJoker.b
      - a.privacy.InfoStealer
    """
    parts = normalized.split(".")
    if len(parts) < 3 or "privacy" not in parts:
        return "unknown"
    token = parts[2].strip().lower()
    if token.startswith("bank") and len(token) > 4:
        token = token[4:]
    elif token.startswith("spy") and len(token) > 3:
        token = token[3:]
    token = FAMILY_ALIAS.get(token, token)
    for fam in KNOWN_FAMILIES:
        if fam in token:
            return fam
    return "unknown"

def parse_tencent_classification(label: str, engine_metadata: Optional[Dict] = None) -> ParsedLabelMetadata:
    result = ParserDefaults.eight_field_fallback()

    if not label or not isinstance(label, str):
        result["edge_case_type"] = "invalid_or_empty"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))

    try:
        normalized = normalize_label(label)
        parts = normalized.split(".")
        parsed = extract_from_structured_parts(parts)

        platform = "android" if "android" in normalized else "unknown"

        # Rule 2: Privacy / grayware prefix pattern
        if parsed["family"] == "unknown" and ("privacy" in normalized or "gray" in normalized):
            privacy_family = _extract_privacy_family_token(normalized)
            if privacy_family != "unknown":
                parsed["family"] = privacy_family

            match = re.search(r"(bank|trojan|spy)([a-z0-9]+)", normalized, re.IGNORECASE)
            if match:
                candidate = match.group(2).lower()
                for known in KNOWN_FAMILIES:
                    if known in candidate:
                        parsed["family"] = known
                        break
            parsed["malware_type"] = "Trojan"
            if "rat" in normalized:
                parsed["threat_class"] = "Rat"
            elif "spy" in normalized:
                parsed["threat_class"] = "Spy"
            elif "stealer" in normalized:
                parsed["threat_class"] = "Stealer"
            elif "bank" in normalized:
                parsed["threat_class"] = "Banker"
            else:
                parsed["threat_class"] = "Unknown"

        # Rule 3: Loose string match
        if parsed["family"] == "unknown":
            parsed["family"] = detect_family_from_fallback(normalized)

        if "rat" in normalized:
            parsed["threat_class"] = "Rat"
            if parsed["malware_type"] in {"unknown", "trojan"}:
                parsed["malware_type"] = "Rat"
            if parsed["family"] == "unknown":
                parsed["family"] = "realrat"

        result.update({
            "malware_type": parsed["malware_type"],
            "threat_class": parsed["threat_class"],
            "platform": platform,
            "family": parsed["family"],
            "variant": parsed["variant"] or "unknown",
            "parser_quality": engine_metadata.get("parser_quality", "medium") if engine_metadata else "medium",
            "signature_type": engine_metadata.get("signature_type", "pattern") if engine_metadata else "pattern"
        })

        result["confidence"] = parser_confidence_estimator.compute_confidence_score(
            label=label,
            parsed_result=result,
            metadata=engine_metadata
        )

    except Exception:
        result = ParserDefaults.eight_field_fallback()
        result["edge_case_type"] = "exception_thrown"

    return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))
