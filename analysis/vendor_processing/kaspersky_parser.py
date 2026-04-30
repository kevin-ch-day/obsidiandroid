# Filename: kaspersky_parser.py
# Description: Parses Kaspersky AV detection strings into structured fields for ObsidianDroid.

from typing import Dict, Optional
from .parser_defaults import ParserDefaults
from . import parser_confidence_estimator
from model.parsing.parsed_label_metadata import ParsedLabelMetadata

# Known family keywords observed in mobile malware samples
FAMILY_KEYWORDS = {
    "hqwar", "mobok", "jocker", "helper", "donot", "revk", "rkor", "bian",
    "spynote", "rewardsteal", "bray", "knobot", "facestealer", "smsthief",
    "cloput", "fakechat", "fakecop", "realrat", "basdoor", "rax", "phonespy",
    "resharer", "masplot", "vuad", "cebruser", "twmobo", "notifyer", "hiddenad",
    "spymax", "techfu", "campys", "monocle", "grifthorse", "bahamut", "goodnews",
    "frikad", "aita", "codoor", "grat", "crydroid", "joker", "exodus", "marcher",
    "sova", "zanubis", "asacub", "gorgona", "yaats", "mandrake", "ghimob",
    "lezok", "riltok", "shopper", "badpack"
}

RAT_FAMILY_HINTS = {
    "realrat", "telerat", "lodarat", "aitarat", "xrat", "gravityrat",
    "androrat", "sandrorat", "onrat", "nanocore", "dcrat", "quasarrat",
}

def sanitize_label(label: str) -> str:
    return label.strip().replace("HEUR:", "").replace("not-a-virus:", "").replace("UDS:", "").replace("_", ".")

def split_classification(label: str) -> list:
    return [p.strip() for p in label.split(".") if p]

def extract_type_block(type_block: str) -> (str, str):
    if "-" in type_block:
        malware_type, threat = type_block.split("-", 1)
        return malware_type.upper(), threat.lower()
    return type_block.upper(), "unknown"

def extract_signature_fields(parts: list) -> Dict[str, str]:
    platform = parts[1].capitalize() if len(parts) > 1 else "unknown"
    if "android" in platform.lower():
        platform = "Android"
    family = parts[2].lower() if len(parts) > 2 else "unknown"
    variant = parts[3].lower() if len(parts) > 3 else "unknown"
    return {
        "platform": platform,
        "family": family,
        "variant": variant
    }

def parse_kaspersky_classification(classification: str, engine_metadata: Optional[Dict] = None) -> ParsedLabelMetadata:
    record = ParserDefaults.eight_field_fallback()
    record["edge_case_type"] = "none"

    if not classification or not isinstance(classification, str):
        record["edge_case_type"] = "empty_or_invalid"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))

    try:
        cleaned = sanitize_label(classification)
        parts = split_classification(cleaned)

        if len(parts) < 3:
            record["edge_case_type"] = "too_few_segments"
            return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))

        malware_type, threat_class = extract_type_block(parts[0])
        sig = extract_signature_fields(parts)

        record.update({
            "malware_type": malware_type,
            "threat_class": threat_class,
            "platform": sig["platform"],
            "variant": sig["variant"],
            "parser_quality": engine_metadata.get("parser_quality", "medium") if engine_metadata else "medium",
            "signature_type": engine_metadata.get("signature_type", "pattern") if engine_metadata else "pattern"
        })

        # Assign family only if it's known
        family = sig["family"]
        if family in FAMILY_KEYWORDS:
            record["family"] = family
        else:
            record["family"] = "unknown"
            record["edge_case_type"] = "unknown_family"

        # Fallback logic using threat_class or variant
        if record["family"] == "unknown":
            fallback = threat_class or sig["variant"]
            if fallback in FAMILY_KEYWORDS:
                record["family"] = fallback
                record["edge_case_type"] = "family_fallback"

        # RAT override: preserve canonical rat semantics on explicit rat-like families.
        fam_lc = str(record.get("family", "")).strip().lower()
        if fam_lc in RAT_FAMILY_HINTS:
            record["threat_class"] = "rat"
            if str(record.get("malware_type", "")).strip().lower() in {
                "trojan", "backdoor", "unknown", ""
            }:
                record["malware_type"] = "rat"

        try:
            record["confidence"] = parser_confidence_estimator.compute_confidence_score(
                label=classification,
                parsed_result=record,
                metadata=engine_metadata
            )
        except Exception:
            record["confidence"] = 0.0
            record["edge_case_type"] = "confidence_fail"

    except Exception:
        fallback = ParserDefaults.eight_field_fallback()
        fallback["edge_case_type"] = "parse_exception"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(fallback))

    return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))
