# Filename: ahnlab_v3_parser.py
# Description: Parser for AhnLab V3 classification labels using confidence estimation

from typing import Dict, Optional
import re

from .parser_defaults import ParserDefaults
from . import parser_confidence_estimator
from obsidiandroid.vendors.contracts.parsed_label_metadata import ParsedLabelMetadata

# Known Malware Families (lowercase)
KNOWN_FAMILIES = {
    "anubis", "cerberus", "sharkbot", "sova", "flubot", "teabot", "joker", "marcher", "vultur",
    "xenomorph", "medusa", "spymax", "monokle", "spyc23.a", "donot", "golddigger", "blankbot",
    "badpack", "cabassous", "clast82", "fatboypanel", "eventbot", "spyloan", "roamingmantis",
    "godfather", "tgtoxic", "irata", "trickmo", "gravityrat", "spyahmyth", "xrat", "ermac",
    "kaishi", "covidspy", "smsthief", "projectspy", "adbeauty", "hiddenads", "fakeyouwon",
    "facestealer", "fakeadblocker", "hidead", "svpeng", "code4hk", "resharer", "bankergf",
    "gigabud", "fjcon", "gravity", "pixbank", "lycoransom", "systemmonitor", "fluhorse", "dmp",
    "finspy", "fakekakao", "addece", "grifthorse", "infostealer", "jystealer", "necro", "synos",
    "iframemal", "kimsuky", "abstractemu", "fakewallet", "smssend", "mobok", "clipper", "boogr",
    "gspy", "telerat", "mobistealth", "beitaad", "hiddensploit", "bahamut", "smsagent", "bankun",
    "stalkspy", "tekya", "sandrorat", "maclt", "crycryptor", "spykids", "tispy", "darkshades",
    "ispytracker", "dendroid", "otpstealer"
}

# Known Threat Classes (lowercase)
THREAT_CLASSES = {
    "banker", "agent", "downloader", "dropper", "malct", "hidap", "locker", "fakeinst",
    "spyagent", "clicker", "mobilespy", "fakeapp", "phishingapp", "facestealer",
    "premiumsms", "smsstealer", "smsspy", "cdwarecrypt", "code4hk", "flprev", "offcamp",
    "tushuad", "ewind", "phonespy", "vserv", "metasploit", "wipelocker", "spynm",
    "sendsms", "andup", "jocker", "revk", "hiddapp"
}

# Regex patterns (primary and reversed)
AHNLAB_PATTERN = re.compile(
    r"(?P<type>\w+)/(?P<platform>Android)\.(?P<family>[A-Za-z0-9_]+)(?:\.(?P<variant>.+))?",
    re.IGNORECASE
)

AHNLAB_REVERSED_PATTERN = re.compile(
    r"(?P<platform>Android)-(?P<type>\w+)/(?P<family>[A-Za-z0-9_]+)(?:\.(?P<variant>.+))?",
    re.IGNORECASE
)

def parse_ahnlab_v3_classification(classification: str, engine_metadata: Optional[Dict] = None) -> ParsedLabelMetadata:
    """
    Parses an AhnLab V3 label string and returns a ParsedLabelMetadata object.
    """
    record = ParserDefaults.eight_field_fallback()

    if not isinstance(classification, str) or not classification.strip():
        record["edge_case_type"] = "empty_or_invalid"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))

    classification = classification.strip()
    match = AHNLAB_PATTERN.match(classification) or AHNLAB_REVERSED_PATTERN.match(classification)

    if not match:
        record["edge_case_type"] = "regex_no_match"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))

    try:
        engine_metadata = engine_metadata if isinstance(engine_metadata, dict) else {}

        # Normalize parsed fields
        record.update({
            "malware_type": match.group("type").capitalize(),
            "platform": match.group("platform").capitalize(),
            "variant": (match.group("variant") or "").strip()
        })

        # Family parsing
        family_token = (match.group("family") or "").strip().lower()

        if family_token in KNOWN_FAMILIES:
            record["family"] = family_token
            record["edge_case_type"] = "structured"
        elif family_token in THREAT_CLASSES:
            record["family"] = "unknown"
            record["threat_class"] = family_token
            record["edge_case_type"] = "generic_family_token"
        else:
            record["family"] = family_token
            record["edge_case_type"] = "unlisted_family"

        # Attach parser metadata
        record["parser_quality"] = engine_metadata.get("parser_quality", "medium")
        record["signature_type"] = engine_metadata.get("signature_type", "pattern")

        # Compute confidence
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
        record = ParserDefaults.eight_field_fallback()
        record["edge_case_type"] = "parse_exception"

    return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))
