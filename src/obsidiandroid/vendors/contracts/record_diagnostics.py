"""Diagnostic mixin for vendor classification records."""

from __future__ import annotations

from typing import Dict, List

GENERIC_FAMILY_SET = {"agent", "generic", "unknown"}
KNOWN_LOW_ENTROPY = {"flubot", "teabot", "vultur", "anubis"}
DEFAULT_CONFIDENCE_THRESHOLD = 0.4


class RecordDiagnosticsMixin:
    def compute_signal_score(self) -> float:
        penalty = 0.25 if getattr(self, "is_generic_family", False) else 0.0
        return round(max(0.0, getattr(self, "confidence_score", 0.0) - penalty), 4)

    @property
    def signal_score(self) -> float:
        return self.compute_signal_score()

    def has_behavior_trait(self, trait: str) -> bool:
        tags = getattr(self, "threat_tags", [])
        return trait.lower() in (t.lower() for t in tags)

    def validate_record_completeness(self) -> str:
        missing = []
        for field in ["family", "malware_type", "threat_class"]:
            val = getattr(self, field, "unknown")
            if not val or str(val).strip().lower() in {"", "unknown"}:
                missing.append(field)
        return "complete" if not missing else f"incomplete ({', '.join(missing)})"

    validate_completeness = validate_record_completeness

    def is_generic_classification(self) -> bool:
        score = getattr(self, "genericity_score", 0)
        family = getattr(self, "family", "").lower()
        return score >= 2 or family in GENERIC_FAMILY_SET

    def is_low_entropy_family(self) -> bool:
        family = getattr(self, "family", "")
        return len(family) <= 5 and family.lower() not in KNOWN_LOW_ENTROPY

    def is_mixed_signal(self) -> bool:
        return (
            getattr(self, "is_valid", False)
            and getattr(self, "is_generic_family", False)
            and getattr(self, "family", "").lower() not in GENERIC_FAMILY_SET
        )

    def is_high_signal(self) -> bool:
        return (
            getattr(self, "is_valid", False)
            and getattr(self, "confidence_score", 0.0) >= 0.7
            and not getattr(self, "is_generic_family", False)
            and getattr(self, "platform", "").strip().lower() == "android"
        )

    def is_low_confidence(self, threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> bool:
        return getattr(self, "confidence_score", 0.0) < threshold

    def get_diagnostic_summary(self) -> str:
        sample_id = getattr(self, "sample_id", "?")
        vendor = getattr(self, "vendor_name", "?")
        family = getattr(self, "family", "").lower()

        if family == "unknown":
            return f"[FAMILY] {sample_id} - Unknown family from vendor {vendor}"
        if self.is_generic_classification():
            return f"[FAMILY] {sample_id} - Generic family '{family}' flagged"
        if self.is_low_entropy_family():
            return f"[FAMILY] {sample_id} - Low-entropy family '{family}'"
        return f"[FAMILY] {sample_id} - Family OK: '{family}'"

    def get_diagnostic_flags(self) -> List[str]:
        flags = []

        family = getattr(self, "family", "").lower()
        platform = getattr(self, "platform", "").lower()
        variant = getattr(self, "variant", "").lower()

        if family == "unknown":
            flags.append("unknown_family")
        if self.is_generic_classification():
            flags.append("generic_family")
        if self.is_low_entropy_family():
            flags.append("low_entropy")
        if self.is_mixed_signal():
            flags.append("mixed_signal")
        if self.is_high_signal():
            flags.append("high_signal")
        if not getattr(self, "is_valid", True):
            flags.append("invalid_record")
        if self.is_low_confidence():
            flags.append("low_confidence")
        if not variant or variant == "unknown":
            flags.append("missing_variant")
        if not platform or platform == "unknown":
            flags.append("unknown_platform")

        return flags

    def get_diagnostic_report(self) -> Dict:
        return {
            "sample_id": getattr(self, "sample_id", "unknown"),
            "vendor_name": getattr(self, "vendor_name", "unknown"),
            "family": getattr(self, "family", "unknown"),
            "confidence": round(getattr(self, "confidence_score", 0.0), 4),
            "signal_score": self.signal_score,
            "flags": ";".join(self.get_diagnostic_flags()),
        }
