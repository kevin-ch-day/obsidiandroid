# Filename: avast_mobile_parser.py
# Description: Parser for Avast Mobile AV classification labels

import re
from typing import Dict, Optional
from .parser_defaults import ParserDefaults
from . import parser_confidence_estimator
from obsidiandroid.vendors.contracts.parsed_label_metadata import ParsedLabelMetadata

TYPE_TAG_MAP = {
    "trj": "trojan", "troj": "trojan", "bank": "banker", "rat": "rat",
    "spy": "spyware", "sms": "sms-trojan", "smsspy": "sms-spy", "drop": "dropper",
    "adw": "adware", "pup": "potentially unwanted", "tool": "hacking tool",
    "fake": "fake-app", "scam": "scam", "ransom": "ransomware", "worm": "worm",
    "bot": "botnet client", "gen": "generic", "heur": "heuristic", "risk": "risky-behavior",
    "warn": "warning", "unw": "unwanted", "mal": "malware", "stalk": "stalkerware"
}

GENERIC_IGNORE = {
    "evo", "evo-gen", "malware-gen", "generic", "repmalware", "repmetagen",
    "apkmalware", "androidmalware", "heuristic"
}

KNOWN_FAMILIES = {
    "anubis", "cerberus", "sharkbot", "sova", "flubot", "teabot", "joker", "marcher", "vultur",
    "xenomorph", "medusa", "monokle", "donot", "godfather", "eventbot", "trickmo", "ermac",
    "spyagent", "spyloan", "spymax", "spyahmyth", "chameleon", "blackrock", "blankbot",
    "brazking", "rafel", "bahamut", "cabassous", "clast82", "golddigger", "fatboypanel",
    "hiddenads", "mobok", "subscriber", "masterfred", "ultimasms", "projectspy", "zoom",
    "icici", "coronavirus", "pakchat", "fakecalls", "fakeplayer", "tgtoxic", "sendsms",
    "xrat", "spyc23.a", "repsandbox"
}

def extract_threat_class(label: str) -> str:
    match = re.search(r'\[(.*?)\]', label)
    if match:
        tag = match.group(1).strip().lower()
        return TYPE_TAG_MAP.get(tag, "unknown")
    return "unknown"

def resolve_family(raw_family: str) -> str:
    rf = raw_family.lower().strip()
    if rf in KNOWN_FAMILIES:
        return rf
    for kf in KNOWN_FAMILIES:
        if rf.startswith(kf):
            return kf
    if rf in GENERIC_IGNORE or rf in {"banker", "malware", "android", "apk"}:
        return "unknown"
    return rf

def parse_avast_mobile_label(label: Optional[str], engine_metadata: Optional[Dict] = None) -> ParsedLabelMetadata:
    result = ParserDefaults.eight_field_fallback()

    if not label or not isinstance(label, str):
        result["edge_case_type"] = "empty_or_invalid"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))

    try:
        label = label.strip()
        result["threat_class"] = extract_threat_class(label)

        label_clean = re.sub(r'\s*\[.*?\]', '', label)

        match = re.match(
            r'(?P<platform>Android|APK|ELF|Other):(?P<family>[A-Za-z0-9]+)(?:[-_](?P<variant>[A-Za-z0-9]+))?',
            label_clean
        )
        if not match:
            result["edge_case_type"] = "regex_no_match"
            return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))

        platform = match.group("platform").capitalize()
        raw_family = match.group("family")
        variant = (match.group("variant") or "unknown").lower()
        variant = "unknown" if len(variant) <= 1 else variant

        result.update({
            "platform": platform,
            "family": resolve_family(raw_family),
            "variant": variant,
            "malware_type": "trojan",
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
        result["edge_case_type"] = "parse_exception"

    return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))
