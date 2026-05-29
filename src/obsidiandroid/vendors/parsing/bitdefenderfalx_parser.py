# Filename: bitdefender_parser.py
# Description: Structured and modular parser for BitDefender.Falx AV labels, optimized for ObsidianDroid malware classification.

import re
from typing import Dict, Optional, List
from .parser_defaults import ParserDefaults
from . import parser_confidence_estimator
from obsidiandroid.vendors.contracts.parsed_label_metadata import ParsedLabelMetadata

TRUE_FAMILIES = {
    "anubis", "cerberus", "eventbot", "sharkbot", "godfather", "teabot",
    "flubot", "chameleon", "blackrock", "ermac", "sova", "brunhilda",
    "spyahmyth", "hqwar", "polph", "marcher", "joker", "vultur",
    "ghimob", "bankbot", "slocker", "spyc23", "spynote", "donot",
    "grifthorse", "androrat", "xenomorph", "mobok", "mandrake",
    "triada", "domestickitten", "bahamut", "bitterrat", "taropeore",
    "bingomod", "systemmonitor", "facestealer", "gravity", "otpstealer"
}

FAMILY_ALIAS_MAP = {
    "spyamyht": "spyahmyth",
    "brunhild": "brunhilda",
    "polph": "polph",
    "teabot": "teabot"
}

GENERIC_TOKENS = {
    "generic", "generickd", "genericfca", "agent", "none",
    "unknown", "hacktool", "spyagent", "infostealer", "dropper",
    "smsspy", "fakeapp", "hiddenapp", "downloader", "obfus", "ransom"
}
THREAT_HINT_TOKENS = {
    "spyagent": "spy",
    "smsspy": "sms-trojan",
    "banker": "banker",
    "infostealer": "stealer",
    "dropper": "dropper",
    "downloader": "downloader",
    "ransom": "ransomware",
    "riskware": "riskware",
    "fakeapp": "fake-app",
}

FAMILY_REGEX_PATTERN = re.compile(
    r"(" + "|".join(TRUE_FAMILIES) + ")", re.IGNORECASE
)

def split_label_parts(label: str) -> List[str]:
    return label.strip().split(".")

def is_numeric_token(token: str) -> bool:
    return token.isdigit() and len(token) >= 4

def resolve_family(candidate: str, full_label: str) -> str:
    norm = candidate.lower()
    if norm in GENERIC_TOKENS or is_numeric_token(norm):
        return "generic"
    if norm in FAMILY_ALIAS_MAP:
        return FAMILY_ALIAS_MAP[norm]
    if norm in TRUE_FAMILIES:
        return norm
    match = FAMILY_REGEX_PATTERN.search(full_label)
    return match.group(1).lower() if match else "unknown"

def infer_threat_class(malware_type: str, family_candidate: str = "") -> str:
    mt = malware_type.lower()
    fc = (family_candidate or "").lower()
    for token, mapped in THREAT_HINT_TOKENS.items():
        if token in fc:
            return mapped
    if "drop" in mt:
        return "dropper"
    if "spy" in mt:
        return "spy"
    if "bank" in mt:
        return "banker"
    if "ransom" in mt:
        return "ransomware"
    if "agent" in mt:
        return "agent"
    return "trojan" if "trojan" in mt else "unknown"

def extract_fields(parts: List[str], full_label: str) -> Dict[str, str]:
    if parts and parts[0].lower() == "android":
        platform = "android"
        malware_type = parts[1].lower() if len(parts) > 1 else "unknown"
        family_candidate = parts[2].lower() if len(parts) > 2 else "unknown"
        variant = ".".join(parts[3:]).lower() if len(parts) > 3 else "unknown"
    else:
        malware_type = parts[0].lower() if len(parts) > 0 else "unknown"
        platform = parts[1].lower() if len(parts) > 1 else "unknown"
        family_candidate = parts[2].lower() if len(parts) > 2 else "unknown"
        variant = ".".join(parts[3:]).lower() if len(parts) > 3 else "unknown"

    return {
        "malware_type": malware_type,
        "platform": platform,
        "family_candidate": family_candidate,
        "variant": variant,
        "family": resolve_family(family_candidate, full_label),
        "threat_class": infer_threat_class(malware_type, family_candidate),
    }

def is_label_edge_case(parts: List[str]) -> bool:
    return (
        len(parts) < 3
        or parts[0].lower() not in {"trojan", "android", "adware", "application"}
        or parts[1].lower() in GENERIC_TOKENS
        or any(not p.strip() for p in parts)
    )

def get_parser_metadata(engine_metadata: Optional[Dict]) -> Dict[str, str]:
    return {
        "parser_quality": engine_metadata.get("parser_quality", "medium") if engine_metadata else "medium",
        "signature_type": engine_metadata.get("signature_type", "pattern") if engine_metadata else "pattern"
    }

def parse_bitdefenderfalx_classification(
    classification: str, engine_metadata: Optional[Dict] = None
) -> ParsedLabelMetadata:
    record = ParserDefaults.eight_field_fallback()

    if not classification or not isinstance(classification, str):
        record["edge_case_type"] = "empty_or_invalid"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))
    label_lc = classification.strip().lower()
    if label_lc in {"undetected", "type-unsupported", "timeout", "failure"}:
        record["edge_case_type"] = "no_detection"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))

    try:
        parts = split_label_parts(classification)
        fields = extract_fields(parts, classification)
        meta = get_parser_metadata(engine_metadata)

        record.update({
            "platform": fields["platform"].capitalize(),
            "malware_type": fields["malware_type"].capitalize(),
            "family": fields["family"],
            "variant": fields["variant"],
            "threat_class": fields["threat_class"],
            "confidence": parser_confidence_estimator.compute_confidence_score(
                label=classification,
                parsed_result=fields,
                metadata=meta
            ),
            **meta,
            "edge_case_type": "bitdefender_generic_numeric" if fields["family"] == "generic" else "none"
        })

        if is_label_edge_case(parts):
            record["parser_quality"] = "low"

    except Exception:
        record = ParserDefaults.eight_field_fallback()
        record["edge_case_type"] = "parse_exception"

    return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))
