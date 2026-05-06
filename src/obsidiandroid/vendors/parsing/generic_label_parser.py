"""Generic fallback parser for AV label strings.

Use this parser for vendors without dedicated parsing logic. It extracts:
- malware_type
- threat_class
- platform
- family (when token matches known family aliases)
- variant (best-effort)
"""

from __future__ import annotations

import re
from typing import Dict, Optional

from .parser_defaults import ParserDefaults
from . import parser_confidence_estimator
from obsidiandroid.vendors.contracts.parsed_label_metadata import ParsedLabelMetadata
from obsidiandroid.labeling.malware_family_constants import FAMILY_ALIASES
from obsidiandroid.labeling.taxonomy import is_known_family_name, normalize_family_name


TOKEN_RE = re.compile(r"[a-z0-9]+")
HEX_RE = re.compile(r"^[a-f0-9]{6,16}$")

NO_DETECTION_TOKENS = {
    "undetected",
    "clean",
    "not-a-virus",
    "notavirus",
    "none",
    "null",
    "n/a",
}

THREAT_KEYWORDS = {
    "rat": "rat",
    "remoteaccess": "rat",
    "remote": "rat",
    "banker": "banker",
    "bankbot": "banker",
    "spy": "spy",
    "spynote": "spy",
    "stealer": "stealer",
    "dropper": "dropper",
    "backdoor": "backdoor",
    "ransom": "ransomware",
    "adware": "adware",
    "sms": "sms-trojan",
    "trojan": "trojan",
    "worm": "worm",
}

THREAT_SUBSTRINGS = (
    ("remoteaccess", "rat"),
    ("androrat", "rat"),
    ("realrat", "rat"),
    ("gravityrat", "rat"),
    ("banker", "banker"),
    ("bankbot", "banker"),
    ("spyagent", "spy"),
    ("smsspy", "sms-trojan"),
    ("smsspy", "sms-trojan"),
    ("spy", "spy"),
    ("agent", "spy"),
    ("dropper", "dropper"),
    ("stealer", "stealer"),
    ("backdoor", "backdoor"),
    ("ransom", "ransomware"),
    ("adware", "adware"),
    ("trojan", "trojan"),
)

MALWARE_TYPE_BY_THREAT = {
    "rat": "rat",
    "banker": "trojan",
    "spy": "trojan",
    "stealer": "trojan",
    "dropper": "trojan",
    "backdoor": "trojan",
    "ransomware": "ransomware",
    "adware": "adware",
    "sms-trojan": "trojan",
    "trojan": "trojan",
    "worm": "worm",
}

NON_FAMILY_TOKENS = {
    "android",
    "trojan",
    "gen",
    "generic",
    "variant",
    "heur",
    "malware",
    "riskware",
    "app",
    "apk",
    "win32",
    "linux",
    "macos",
    "java",
    "agent",
}


def _normalize_text(label: str) -> str:
    clean = str(label or "").strip().lower()
    clean = clean.replace("androidos", "android")
    clean = clean.replace("android.", "android/")
    clean = clean.replace("remote-access", "remoteaccess")
    clean = clean.replace("remote access", "remoteaccess")
    return clean


def _infer_platform(text: str) -> str:
    if "android" in text or "apk" in text:
        return "android"
    if "win32" in text or "windows" in text:
        return "windows"
    return "unknown"


def _infer_threat(tokens: list[str]) -> str:
    for token in tokens:
        if token in THREAT_KEYWORDS:
            return THREAT_KEYWORDS[token]
    joined = " ".join(tokens)
    for marker, threat in THREAT_SUBSTRINGS:
        if marker in joined:
            return threat
    return "unknown"


def _infer_family(tokens: list[str], text: str) -> str:
    for token in tokens:
        if token in NON_FAMILY_TOKENS or len(token) < 3:
            continue
        mapped = FAMILY_ALIASES.get(token, token)
        canonical = normalize_family_name(mapped)
        if canonical and is_known_family_name(canonical):
            return canonical

    # DrWeb-like pattern: Android.BankBot.<family>.<variant>.origin
    bankbot_match = re.search(r"android[./]bankbot[./]([a-z0-9_]+)", text)
    if bankbot_match:
        candidate = normalize_family_name(bankbot_match.group(1))
        if candidate and candidate not in NON_FAMILY_TOKENS:
            return candidate

    # Fortinet/ESET-like pattern where family may appear after threat token.
    seq_tokens = [t for t in tokens if t and t not in NON_FAMILY_TOKENS]
    for idx, token in enumerate(seq_tokens[:-1]):
        if token in {"banker", "bankbot", "spy", "spyagent", "dropper", "stealer"}:
            candidate = normalize_family_name(seq_tokens[idx + 1])
            if candidate and len(candidate) >= 5 and candidate not in NON_FAMILY_TOKENS:
                return candidate
    return "unknown"


def _infer_variant(tokens: list[str]) -> str:
    # Prefer compact hash-like tokens as variant hints.
    for token in reversed(tokens):
        if HEX_RE.match(token):
            return token
    # Fallback to final long token if it is not too generic.
    for token in reversed(tokens):
        if len(token) >= 6 and token not in NON_FAMILY_TOKENS:
            return token
    return "unknown"


def parse_generic_classification(
    classification: str,
    engine_metadata: Optional[Dict] = None,
) -> ParsedLabelMetadata:
    """Parse a vendor label using generic token heuristics."""
    record = ParserDefaults.eight_field_fallback()
    record["edge_case_type"] = "none"

    if not classification or not isinstance(classification, str):
        record["edge_case_type"] = "empty_or_invalid"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))

    text = _normalize_text(classification)
    if text in NO_DETECTION_TOKENS:
        record["edge_case_type"] = "no_detection"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))

    tokens = TOKEN_RE.findall(text)
    if not tokens:
        record["edge_case_type"] = "no_tokens"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))

    threat_class = _infer_threat(tokens)
    malware_type = MALWARE_TYPE_BY_THREAT.get(threat_class, "trojan" if threat_class != "unknown" else "unknown")
    family = _infer_family(tokens, text)
    variant = _infer_variant(tokens)
    platform = _infer_platform(text)

    record.update(
        {
            "malware_type": malware_type,
            "threat_class": threat_class,
            "platform": platform,
            "family": family,
            "variant": variant,
            "parser_quality": (
                engine_metadata.get("parser_quality", "low")
                if engine_metadata
                else "low"
            ),
            "signature_type": (
                engine_metadata.get("signature_type", "generic")
                if engine_metadata
                else "generic"
            ),
        }
    )

    if threat_class == "rat" and malware_type in {"unknown", "trojan", "backdoor"}:
        record["malware_type"] = "rat"

    try:
        record["confidence"] = parser_confidence_estimator.compute_confidence_score(
            label=classification,
            parsed_result=record,
            metadata=engine_metadata,
        )
    except Exception:
        record["confidence"] = 0.0
        record["edge_case_type"] = "confidence_fail"

    return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(record))
