# Filename: parser_defaults.py
# Description: Shared fallback templates and normalization utilities for AV label parsing in ObsidianDroid

from typing import Dict, Optional, Union

class ParserDefaults:
    DEFAULT_UNKNOWN = "unknown"

    # --------------------------------------
    # Core Fallback Templates
    # --------------------------------------

    @classmethod
    def four_part(cls, extra: Optional[str] = None) -> Dict[str, str]:
        """
        Base 4-field structure (with optional extra field).
        """
        base = {
            "malware_type": cls.DEFAULT_UNKNOWN,
            "platform": cls.DEFAULT_UNKNOWN,
            "family": cls.DEFAULT_UNKNOWN,
            "variant": cls.DEFAULT_UNKNOWN
        }
        if extra:
            base[extra] = cls.DEFAULT_UNKNOWN
        return base

    @classmethod
    def five_part(cls) -> Dict[str, str]:
        """
        Adds 'ability' to core fields — used for legacy/heuristic-based detection.
        """
        return {
            "malware_type": cls.DEFAULT_UNKNOWN,
            "ability": cls.DEFAULT_UNKNOWN,
            "platform": cls.DEFAULT_UNKNOWN,
            "family": cls.DEFAULT_UNKNOWN,
            "variant": cls.DEFAULT_UNKNOWN
        }

    @classmethod
    def eight_field_fallback(cls) -> Dict[str, Union[str, float]]:
        """
        Full record template including parser metadata, scoring, and edge handling.
        """
        return {
            "malware_type": cls.DEFAULT_UNKNOWN,
            "threat_class": cls.DEFAULT_UNKNOWN,
            "ability": cls.DEFAULT_UNKNOWN,
            "platform": cls.DEFAULT_UNKNOWN,
            "family": cls.DEFAULT_UNKNOWN,
            "variant": "",
            "confidence": 0.5,
            "parser_quality": "low",
            "signature_type": "unknown",
            "edge_case_type": "fallback"
        }

    @classmethod
    def with_metadata(cls, include_score: bool = False, confidence: float = 0.5) -> Dict[str, Union[str, float]]:
        """
        5-part structure with optional scoring and metadata fields.
        """
        base = cls.five_part()
        if include_score:
            base["confidence"] = round(confidence, 2)
            base["parser_quality"] = "medium"
            base["signature_type"] = "pattern"
        return base

    # --------------------------------------
    # Record Normalization Utilities
    # --------------------------------------

    @staticmethod
    def normalize(record: Dict[str, Union[str, float]]) -> Dict[str, Union[str, float]]:
        """
        Normalize record fields: lowercase, default unknown, confidence rounded.
        """
        platform_aliases = {
            "androidos": "android",
            "android": "android",
            "andr": "android",
            "apk": "android",
        }
        threat_aliases = {
            "remote-access trojan": "rat",
            "remote access trojan": "rat",
            "remote-access": "rat",
            "remote access": "rat",
            "androrat": "rat",
            "realrat": "rat",
        }
        malware_type_aliases = {
            "trojanspy": "trojan",
            "trojan-spy": "trojan",
            "android": "trojan",
            "andr": "trojan",
        }

        normalized = {}
        for key, value in record.items():
            val = str(value).strip() if value is not None else ""

            if key == "confidence":
                try:
                    normalized[key] = round(float(value), 2)
                except (ValueError, TypeError):
                    normalized[key] = 0.0
            elif not val:
                normalized[key] = ParserDefaults.DEFAULT_UNKNOWN
            elif key == "family":
                normalized[key] = val.lower().title()
            elif key == "variant":
                normalized[key] = val.lower()
            elif key == "platform":
                token = val.lower()
                normalized[key] = platform_aliases.get(token, token)
            elif key == "threat_class":
                token = val.lower()
                normalized[key] = threat_aliases.get(token, token)
            elif key == "malware_type":
                token = val.lower()
                normalized[key] = malware_type_aliases.get(token, token)
            else:
                normalized[key] = val
        return normalized

    @staticmethod
    def add_confidence(record: Dict[str, str], score: float = 0.5) -> Dict[str, Union[str, float]]:
        """
        Adds or updates the confidence score field in a record.
        """
        record = record.copy()
        record["confidence"] = round(score, 2)
        return record

    @staticmethod
    def boost_confidence_if_match(record: Dict[str, str], ground_truth: str, base_score: float = 0.6) -> Dict[str, Union[str, float]]:
        """
        Boosts confidence score to 1.0 if family matches ground truth.
        """
        record = record.copy()
        predicted = record.get("family", "").strip().lower()
        truth = ground_truth.strip().lower()
        record["confidence"] = 1.0 if predicted == truth else base_score
        return record

    # --------------------------------------
    # Field Patchers & Merge Utilities
    # --------------------------------------

    @staticmethod
    def set_if_unknown(record: Dict[str, str], field: str, value: str) -> None:
        """
        Assign value if field is missing or marked unknown.
        """
        if record.get(field, "").strip().lower() in {"", "unknown"} and value:
            record[field] = value.strip()

    @staticmethod
    def merge_parsed_fields(base: Dict[str, str], override: Dict[str, str]) -> Dict[str, str]:
        """
        Merge parsed override values into base if fields are empty or unknown.
        """
        merged = base.copy()
        for k, v in override.items():
            if merged.get(k, "").strip().lower() in {"", "unknown"} and str(v).strip():
                merged[k] = str(v).strip()
        return merged

    @staticmethod
    def apply_aliases(record: Dict[str, str], alias_map: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Rewrites fields like family or ability using alias maps.
        """
        if not alias_map:
            return record
        record = record.copy()
        for field in ["family", "ability"]:
            val = record.get(field, "").lower()
            if val in alias_map:
                record[field] = alias_map[val]
        return record

    # --------------------------------------
    # Record Validation
    # --------------------------------------

    @staticmethod
    def is_incomplete(record: Dict[str, str]) -> bool:
        """
        Detects if any required field is missing or unknown.
        """
        return any(
            isinstance(val, str) and val.strip().lower() in {"", "unknown"}
            for val in record.values()
        )
