# Filename: bitdefender_parser.py
# Description: Structured parser for BitDefender.Falx AV labels (VirusTotal static results)

import re
from typing import Dict, Optional, List
from .parser_defaults import ParserDefaults
from . import parser_confidence_estimator
from obsidiandroid.vendors.contracts.parsed_label_metadata import ParsedLabelMetadata

TRUE_FAMILIES = {
    "anubis", "cerberus", "eventbot", "sharkbot", "godfather", "teabot",
    "flubot", "chameleon", "blackrock", "ermac", "sova", "brunhilda",
    "spyahmyth", "hqwar", "polph", "otpstealer"
}

FAMILY_ALIAS_MAP = {
    "spyamyht": "spyahmyth", "brunhild": "brunhilda", "polph": "polph", "teabot": "teabot"
}

GENERIC_TOKENS = {"generic", "generickd", "genericfca", "agent", "none", "unknown", "hacktool"}
THREAT_HINT_TOKENS = {
    "agent": "agent",
    "banker": "banker",
    "spy": "spy",
    "dropper": "dropper",
    "downloader": "downloader",
    "ransom": "ransomware",
    "adware": "adware",
}

FAMILY_REGEX_PATTERN = re.compile(
    r"(anubis|cerberus|eventbot|sharkbot|godfather|teabot|flubot|ermac|sova|brunhilda|chameleon|blackrock|spyahmyth|hqwar|polph|otpstealer)",
    re.IGNORECASE
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
    if match:
        return match.group(1).lower()
    return "unknown"

def infer_threat_class(malware_type: str, threat_hint: str = "") -> str:
    mt = malware_type.lower()
    hint = (threat_hint or "").lower()
    for token, mapped in THREAT_HINT_TOKENS.items():
        if token in hint:
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
    malware_type = parts[0].lower() if len(parts) > 0 else "unknown"
    platform = parts[1].lower() if len(parts) > 1 else "unknown"
    family_candidate = parts[2].lower() if len(parts) > 2 else "unknown"
    threat_hint = parts[1].lower() if len(parts) > 1 else ""
    variant = ".".join(parts[3:]).lower() if len(parts) > 3 else "unknown"
    return {
        "malware_type": malware_type,
        "platform": platform,
        "family_candidate": family_candidate,
        "variant": variant,
        "family": resolve_family(family_candidate, full_label),
        "threat_class": infer_threat_class(malware_type, threat_hint),
    }

def is_label_edge_case(parts: List[str]) -> bool:
    return (
        len(parts) < 3
        or parts[0].lower() not in {"trojan", "android", "adware", "application"}
        or parts[1].lower() in GENERIC_TOKENS
        or any(p.strip() == "" for p in parts)
    )

def get_parser_metadata(engine_metadata: Optional[Dict]) -> Dict[str, str]:
    return {
        "parser_quality": engine_metadata.get("parser_quality", "medium") if engine_metadata else "medium",
        "signature_type": engine_metadata.get("signature_type", "pattern") if engine_metadata else "pattern"
    }

def parse_bitdefender_classification(
    classification: str, engine_metadata: Optional[Dict] = None
) -> ParsedLabelMetadata:
    result = ParserDefaults.eight_field_fallback()

    if not classification or not isinstance(classification, str):
        result["edge_case_type"] = "empty_or_invalid"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))
    label_lc = classification.strip().lower()
    if label_lc in {"undetected", "type-unsupported", "timeout", "failure"}:
        result["edge_case_type"] = "no_detection"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))

    try:
        parts = split_label_parts(classification)
        if len(parts) < 2:
            result["parser_quality"] = "low"
            result["edge_case_type"] = "too_short"
            return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))

        fields = extract_fields(parts, classification)
        meta = get_parser_metadata(engine_metadata)

        result.update({
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
            result["parser_quality"] = "low"

    except Exception:
        result = ParserDefaults.eight_field_fallback()
        result["edge_case_type"] = "parse_exception"

    return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))
