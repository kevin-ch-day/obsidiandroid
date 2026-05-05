# Filename: k7gw_parser.py
# Description: Parser for K7GW antivirus label strings with classification, confidence scoring, and signature-to-family mapping.

from typing import Dict, Optional, Tuple
from .parser_defaults import ParserDefaults
from . import parser_confidence_estimator
from obsidiandroid.vendors.contracts.parsed_label_metadata import ParsedLabelMetadata

THREAT_CLASS_MAP = {
    "trojan": "trojan",
    "spyware": "spy",
    "adware": "adware",
    "trojan-downloader": "downloader",
    "dropper": "dropper",
    "worm": "worm",
    "ransom": "ransomware",
    "generic": "unknown",
    "none": "unknown"
}

SIGNATURE_FAMILY_MAP = {
    "0058ee3b1": "irata",
    "0059e3141": "gigabud",
    "0059cb701": "pixpirate",
    "0059be201": "pixpirate",
    "00533c4a1": "monokle",
    "0059f1671": "tgtoxic",
    "0058258c1": "irata",
    "005a1b9b1": "gigabud",
    "0058cfb51": "irata",
    "004c91f91": "xrat",
    "0059a0511": "fatboypanel",
    "005ad4e41": "golddigger",
    "005a3e401": "donot",
    "00524d4d1": "marcher",
    "005a8f7f1": "godfather",
    "005164a71": "eventbot",
    "005b0dd61": "vultur",
    "005a3def1": "golddigger",
    "0001140e1": "unknown_malformed"
}

def extract_label_components(label: str) -> Tuple[str, str]:
    if not label or not isinstance(label, str):
        return "none", "none"
    label = label.strip()
    if "(" in label and ")" in label:
        try:
            type_part = label.split("(", 1)[0].strip().lower()
            sig_part = label.split("(", 1)[1].split(")", 1)[0].strip().lower()
            return type_part or "none", sig_part or "none"
        except Exception:
            return "none", "none"
    return label.lower(), "none"

def normalize_threat_class(raw_type: str) -> str:
    return THREAT_CLASS_MAP.get(raw_type.strip().lower(), "unknown")

def validate_signature_id(sig: str) -> str:
    sig = str(sig).strip().lower()
    if len(sig) < 4 or not sig.isalnum() or sig in {"none", "null"}:
        return "none"
    return sig

def get_parser_metadata(engine_metadata: Optional[Dict]) -> Dict[str, str]:
    return {
        "parser_quality": engine_metadata.get("parser_quality", "baseline") if engine_metadata else "baseline",
        "signature_type": engine_metadata.get("signature_type", "pattern") if engine_metadata else "pattern"
    }

def infer_family_from_signature(sig_id: str) -> str:
    return SIGNATURE_FAMILY_MAP.get(sig_id, "unknown")

def build_base_parsing_result(sig_id: str, raw_type: str) -> Dict[str, str]:
    return {
        "variant": sig_id,
        "threat_class": normalize_threat_class(raw_type),
        "malware_type": "malware",
        "platform": "android",
        "family": infer_family_from_signature(sig_id),
        "edge_case_type": "signature_missing" if sig_id == "none" else "none"
    }

def enrich_with_metadata_and_confidence(parsed_result: Dict[str, str], label: str, engine_metadata: Optional[Dict]) -> Dict[str, str]:
    meta = get_parser_metadata(engine_metadata)
    parsed_result.update(meta)
    try:
        parsed_result["confidence"] = parser_confidence_estimator.compute_confidence_score(
            label=label,
            parsed_result=parsed_result,
            metadata=meta
        )
    except Exception:
        parsed_result["confidence"] = 0.0
        parsed_result["edge_case_type"] = "confidence_fail"
    return ParserDefaults.normalize(parsed_result)

def parse_k7gw_classification(label: str, engine_metadata: Optional[Dict] = None) -> ParsedLabelMetadata:
    try:
        type_part, raw_signature = extract_label_components(label)
        valid_sig = validate_signature_id(raw_signature)
        result = build_base_parsing_result(valid_sig, type_part)
        enriched = enrich_with_metadata_and_confidence(result, label, engine_metadata)
        return ParsedLabelMetadata.from_dict(enriched)
    except Exception:
        fallback = ParserDefaults.eight_field_fallback()
        fallback["edge_case_type"] = "parse_exception"
        return ParsedLabelMetadata.from_dict(ParserDefaults.normalize(fallback))
