# Filename: zonealarm_parser.py
# Description: Parser for ZoneAlarm AV classification labels with confidence scoring

from typing import Dict, Optional
from .parser_defaults import ParserDefaults
from . import parser_confidence_estimator
from obsidiandroid.vendors.contracts.parsed_label_metadata import ParsedLabelMetadata

KNOWN_ABILITIES = {
    "banker", "agent", "dropper", "spy", "downloader", "ransom", "backdoor",
    "risktool", "monitor", "mmonitor", "adware", "fakeapp", "boogr", "callerspy",
    "hiddapp", "xgen", "xgen2", "kylk", "cookiethief", "hawkshaw", "spyagnt",
    "dropr", "dloadr", "hiddad", "smforw", "grat", "prmsvc"
}

FAMILY_KEYWORDS = {
    "clast82", "hqwar", "piom", "mocen", "mobok", "jocker", "helper", "donot",
    "revk", "rkor", "bian", "spynote", "rewardsteal", "bray", "knobot", "facestealer",
    "smsthief", "cloput", "fakechat", "fakecop", "realrat", "basdoor", "rax", "phonespy",
    "resharer", "masplot", "vuad", "cebruser", "twmobo", "notifyer", "hiddenad", "spymax",
    "techfu", "campys", "monocle", "grifthorse", "bahamut", "goodnews", "frikad", "aita",
    "codoor", "grat", "crydroid", "joker", "exodus", "marcher", "sova", "zanubis",
    "asacub", "gorgona", "yaats", "mandrake", "ghimob", "lezok", "riltok", "shopper",
    "badpack", "godfather", "xhelper", "pigetrl", "wroba", "anubis", "gigabud", "monocle",
    "basbanke", "banbra", "brats", "smaps", "drinik", "ghimob", "donot", "yaats",
    "aitarat", "triada", "facestealer", "fakewallet", "guerrilla", "strongpity", "freecash",
    "grifthorse", "dnotua", "mobhey", "trackplus", "teddad", "otpstealer"
}

THREAT_CLASS_ALIASES = {
    "androrat": "rat",
    "realrat": "rat",
    "aitarat": "rat",
    "rat": "rat",
    "spy": "spy",
    "banker": "banker",
}

RAT_FAMILY_HINTS = {
    "realrat", "telerat", "lodarat", "aitarat", "xrat", "gravityrat",
    "androrat", "sandrorat", "onrat", "nanocore", "dcrat", "quasarrat",
}

def parse_zonealarm_classification(classification: str, engine_metadata: Optional[Dict] = None) -> ParsedLabelMetadata:
    result = ParserDefaults.eight_field_fallback()

    if not classification or not isinstance(classification, str):
        result["edge_case_type"] = "empty_or_invalid"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))

    try:
        label = classification.replace("HEUR:", "").replace("not-a-virus:", "").replace(":", "").strip()

        # Case 1: Andr/AndroRAT-P or Andr/Banker-GXW
        if "/" in label and "-" in label:
            mal_type, rest = label.split("/", 1)
            threat_part, variant = rest.split("-", 1)
            mal_norm = mal_type.strip().lower()
            threat_norm = threat_part.strip().lower()
            result["malware_type"] = "trojan" if mal_norm in {"andr", "android"} else mal_norm
            result["platform"] = "android" if mal_norm in {"andr", "android"} else result["platform"]
            result["threat_class"] = THREAT_CLASS_ALIASES.get(threat_norm, threat_norm)
            result["variant"] = variant.strip().lower()
            if "rat" in threat_norm:
                result["malware_type"] = "rat"
                result["family"] = threat_norm

        # Case 2: Trojan-Banker.AndroidOS.Anubis.r
        elif "-" in label and "." in label:
            threat_info, *parts = label.split(".")
            if "-" in threat_info:
                mal_type, threat_class = threat_info.split("-", 1)
                result["malware_type"] = mal_type.strip().lower()
                result["threat_class"] = THREAT_CLASS_ALIASES.get(
                    threat_class.strip().lower(),
                    threat_class.strip().lower(),
                )
            else:
                result["malware_type"] = threat_info.strip().lower()

            if len(parts) >= 1:
                platform_raw = parts[0].strip().lower()
                result["platform"] = "android" if platform_raw in {"androidos", "android", "andr"} else platform_raw
            if len(parts) >= 2:
                result["family"] = parts[1].strip().lower()
            if len(parts) >= 3:
                result["variant"] = parts[2].strip().lower()

        # Case 3: Trojan.AndroidOS.Agent.gt
        elif "." in label:
            parts = label.split(".")
            if len(parts) >= 1:
                result["malware_type"] = parts[0].strip().lower()
            if len(parts) >= 2:
                platform_raw = parts[1].strip().lower()
                result["platform"] = "android" if platform_raw in {"androidos", "android", "andr"} else platform_raw
            if len(parts) >= 3:
                result["family"] = parts[2].strip().lower()
            if len(parts) >= 4:
                result["variant"] = parts[3].strip().lower()

        # Fallback family guess logic
        if not result["family"]:
            guess = result.get("threat_class", "") or result.get("variant", "")
            guess = guess.lower()
            if guess in KNOWN_ABILITIES or guess in FAMILY_KEYWORDS:
                result["family"] = guess

        # Canonicalize rat semantics
        if "rat" in str(result.get("threat_class", "")).lower():
            result["threat_class"] = "rat"
            if result.get("malware_type", "") in {"trojan", "andr", "android"}:
                result["malware_type"] = "rat"
        fam_lc = str(result.get("family", "")).strip().lower()
        if fam_lc in RAT_FAMILY_HINTS:
            result["threat_class"] = "rat"
            if str(result.get("malware_type", "")).strip().lower() in {"trojan", "andr", "android", "backdoor", "unknown", ""}:
                result["malware_type"] = "rat"

        # Attach metadata and confidence
        result["parser_quality"] = engine_metadata.get("parser_quality", "medium") if engine_metadata else "medium"
        result["signature_type"] = engine_metadata.get("signature_type", "pattern") if engine_metadata else "pattern"
        result["confidence"] = parser_confidence_estimator.compute_confidence_score(
            label=classification,
            parsed_result=result,
            metadata=engine_metadata
        )

    except Exception:
        result = ParserDefaults.eight_field_fallback()
        result["edge_case_type"] = "parse_exception"

    return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(result))
