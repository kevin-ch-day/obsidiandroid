# Filename: ikarus_parser.py
# Description: Parses Ikarus AV classification labels into structured, normalized threat metadata.

from typing import Dict, Optional
from .parser_defaults import ParserDefaults
from . import parser_confidence_estimator
from model.parsing.parsed_label_metadata import ParsedLabelMetadata

# Normalized threat class mapping
ABILITY_NORMALIZATION = {
    "banker": "banker",
    "spy": "spyware",
    "dropper": "dropper",
    "downloader": "downloader",
    "ransom": "ransomware",
    "sms": "sms-trojan",
    "rat": "rat",
    "clicker": "clicker",
    "locker": "locker",
    "agent": "generic agent",
    "monitor": "monitoring",
    "adware": "adware",
    "backdoor": "backdoor"
}

# Generic family terms to suppress
GENERIC_FAMILY_IGNORE = {
    "agent", "banker", "clicker", "dropper", "locker", "obfus", "spy", "monitor"
}

# Banking trojan family whitelist
KNOWN_FAMILIES = {
    "anubis", "cerberus", "sharkbot", "sova", "flubot", "teabot", "joker", "marcher",
    "vultur", "xenomorph", "medusa", "monokle", "donot", "godfather", "eventbot",
    "trickmo", "ermac", "spymax", "spyloan", "clast82", "cabassous", "golddigger",
    "blackrock", "blankbot", "bahamut", "rafel", "spyagent", "chameleon", "mobok",
    "fatboypanel", "masterfred", "icici", "fakecalls", "zoom", "pakchat", "tgtoxic",
    "fakeplayer", "sendsms", "xrat"
}

RAT_FAMILY_HINTS = {
    "realrat", "telerat", "lodarat", "aitarat", "xrat", "gravityrat",
    "androrat", "sandrorat", "onrat", "nanocore", "dcrat", "quasarrat",
}

def normalize_family_name(family: str) -> str:
    family = family.strip().lower()
    if family in GENERIC_FAMILY_IGNORE:
        return "unknown"
    if family in KNOWN_FAMILIES:
        return family
    for known in KNOWN_FAMILIES:
        if family.startswith(known):
            return known
    return family or "unknown"

def parse_ikarus_classification(classification: str, engine_metadata: Optional[Dict] = None) -> ParsedLabelMetadata:
    record = ParserDefaults.eight_field_fallback()

    if not classification or not isinstance(classification, str):
        record["edge_case_type"] = "empty_or_invalid"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))

    try:
        label = classification.strip()

        # Step 1: Prefix parsing
        if '-' in label.split('.', 1)[0]:
            prefix_block, remainder = label.split('.', 1)
            type_parts = prefix_block.split('-')

            record["malware_type"] = type_parts[0].strip().capitalize()
            if len(type_parts) > 1:
                ability = type_parts[1].strip().lower()
                record["threat_class"] = ABILITY_NORMALIZATION.get(ability, ability)
        else:
            remainder = label

        # Step 2: Android platform detection
        if "AndroidOS." in remainder:
            record["platform"] = "Android"
            remainder = remainder.split("AndroidOS.", 1)[-1]
        else:
            record["platform"] = "unknown"

        # Step 3: Family and variant parsing
        parts = remainder.split('.')
        if len(parts) >= 1:
            record["family"] = normalize_family_name(parts[0])
        if len(parts) >= 2:
            record["variant"] = parts[1].lower().strip()

        fam_lc = str(record.get("family", "")).strip().lower()
        if fam_lc in RAT_FAMILY_HINTS:
            record["threat_class"] = "rat"
            if str(record.get("malware_type", "")).strip().lower() in {
                "trojan", "backdoor", "unknown", ""
            }:
                record["malware_type"] = "rat"

        # Step 4: Attach parser metadata
        record["parser_quality"] = engine_metadata.get("parser_quality", "medium") if engine_metadata else "medium"
        record["signature_type"] = engine_metadata.get("signature_type", "pattern") if engine_metadata else "pattern"

        # Step 5: Confidence scoring
        record["confidence"] = parser_confidence_estimator.compute_confidence_score(
            label=label,
            parsed_result=record,
            metadata=engine_metadata
        )

    except Exception:
        record = ParserDefaults.eight_field_fallback()
        record["edge_case_type"] = "parse_exception"

    return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))
