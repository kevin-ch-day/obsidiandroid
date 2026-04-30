# Filename: model/metadata_normalizer.py

import re
from typing import Optional, Union

class ParsedMetadataNormalizer:

    DEFAULT_UNKNOWN = "unknown"
    GENERIC_FAMILIES = {"unknown", "generic", "agent"}
    WEAK_QUALITIES = {"low", "unknown"}

    @staticmethod
    def normalize_field(value: Optional[str], default: str = DEFAULT_UNKNOWN) -> str:
        return (value or default).strip().lower() or default

    @classmethod
    def is_generic_family(cls, family: str) -> bool:
        return cls.normalize_field(family) in cls.GENERIC_FAMILIES

    @classmethod
    def is_low_quality_parser(cls, parser_quality: str) -> bool:
        return cls.normalize_field(parser_quality) in cls.WEAK_QUALITIES

    @classmethod
    def adjust_confidence_score(
        cls,
        conf: Union[float, None],
        is_generic: bool,
        is_weak: bool,
        return_reason: bool = False
    ) -> Union[float, tuple[float, str]]:
        """
        Adjusts the confidence score based on genericity and parser quality.
        If return_reason is True, also returns a textual explanation of the adjustment.
        """
        # Validate input
        score = float(conf or 0.0)
        reason_parts = []

        if is_generic:
            score -= 0.1
            reason_parts.append("generic_penalty")

        if is_weak:
            score -= 0.1
            reason_parts.append("weak_parser_penalty")

        score = round(max(0.0, min(score, 1.0)), 4)
        reason = "+".join(reason_parts) if reason_parts else "base"

        return (score, reason) if return_reason else score

    @staticmethod
    def infer_variant_from_label(label: str, family: str = "", min_len: int = 6, max_len: int = 12) -> str:
        """
        Extracts a likely variant ID from the end of an AV label string.
        """
        if not label:
            return ""
        label = label.lower()

        # Match patterns like: Android.Banker.abcdef12 or .abcdef
        pattern = rf'\.(?:{re.escape(family)})?\.(?P<variant>[a-f0-9]{{{min_len},{max_len}}})$'
        match = re.search(pattern, label)
        if match:
            return match.group("variant")

        # Fallback: take last dot-delimited token
        tokens = label.split('.')
        last_token = tokens[-1]
        if re.fullmatch(rf'[a-f0-9]{{{min_len},{max_len}}}', last_token):
            return last_token
        return ""

    @classmethod
    def determine_variant(cls, metadata_variant: str, original_label: str, family: str) -> str:
        """
        Returns a normalized variant string, inferred from label if needed.
        """
        norm_variant = cls.normalize_field(metadata_variant, cls.DEFAULT_UNKNOWN)
        if norm_variant != cls.DEFAULT_UNKNOWN:
            return norm_variant
        inferred = cls.infer_variant_from_label(original_label, family)
        return inferred or cls.DEFAULT_UNKNOWN
