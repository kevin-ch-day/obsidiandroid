# Filename: model/record_diagnostics.py
# Purpose : Diagnostic logic for classification record validation, signal scoring, and confidence analysis

from typing import List, Dict

GENERIC_FAMILY_SET = {"agent", "generic", "unknown"}
KNOWN_LOW_ENTROPY = {"flubot", "teabot", "vultur", "anubis"}

# Confidence threshold used across diagnostic logic
DEFAULT_CONFIDENCE_THRESHOLD = 0.4


class RecordDiagnosticsMixin:
    def compute_signal_score(self) -> float:
        """
        Computes confidence-adjusted signal score, penalizing generic classifications.
        """
        penalty = 0.25 if getattr(self, "is_generic_family", False) else 0.0
        return round(max(0.0, getattr(self, "confidence_score", 0.0) - penalty), 4)

    @property
    def signal_score(self) -> float:
        """
        Property-style access to computed signal score (used in export and evaluation).
        """
        return self.compute_signal_score()

    def has_behavior_trait(self, trait: str) -> bool:
        """
        Checks if a specific behavioral trait is present in the record's threat tags.
        """
        tags = getattr(self, "threat_tags", [])
        return trait.lower() in (t.lower() for t in tags)

    def validate_record_completeness(self) -> str:
        """
        Checks whether critical classification fields are non-empty and valid.
        Returns:
            'complete' or 'incomplete (<missing fields>)'
        """
        missing = []
        for field in ["family", "malware_type", "threat_class"]:
            val = getattr(self, field, "unknown")
            if not val or str(val).strip().lower() in {"", "unknown"}:
                missing.append(field)
        return "complete" if not missing else f"incomplete ({', '.join(missing)})"

    # Legacy alias
    validate_completeness = validate_record_completeness

    def is_generic_classification(self) -> bool:
        """
        Determines if family is flagged as generic, using score or known generic values.
        """
        score = getattr(self, "genericity_score", 0)
        family = getattr(self, "family", "").lower()
        return score >= 2 or family in GENERIC_FAMILY_SET

    def is_low_entropy_family(self) -> bool:
        """
        Flags short family names that are unlikely to be meaningful (unless whitelisted).
        """
        family = getattr(self, "family", "")
        return len(family) <= 5 and family.lower() not in KNOWN_LOW_ENTROPY

    def is_mixed_signal(self) -> bool:
        """
        Detects records that are valid but have weak (generic) family labels.
        """
        return getattr(self, "is_valid", False) and getattr(self, "is_generic_family", False) and \
               getattr(self, "family", "").lower() not in GENERIC_FAMILY_SET

    def is_high_signal(self) -> bool:
        """
        Detects strong signals: high confidence, Android platform, non-generic families.
        """
        return (
            getattr(self, "is_valid", False) and
            getattr(self, "confidence_score", 0.0) >= 0.7 and
            not getattr(self, "is_generic_family", False) and
            getattr(self, "platform", "").strip().lower() == "android"
        )

    def is_low_confidence(self, threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> bool:
        """
        Determines if the confidence score falls below the specified threshold.
        """
        return getattr(self, "confidence_score", 0.0) < threshold

    def get_diagnostic_summary(self) -> str:
        """
        Simple debug line showing family status and sample ID.
        """
        sample_id = getattr(self, "sample_id", "?")
        vendor = getattr(self, "vendor_name", "?")
        family = getattr(self, "family", "").lower()

        if family == "unknown":
            return f"[FAMILY] {sample_id} – Unknown family from vendor {vendor}"
        if self.is_generic_classification():
            return f"[FAMILY] {sample_id} – Generic family '{family}' flagged"
        if self.is_low_entropy_family():
            return f"[FAMILY] {sample_id} – Low-entropy family '{family}'"
        return f"[FAMILY] {sample_id} – Family OK: '{family}'"

    def get_diagnostic_flags(self) -> List[str]:
        """
        Returns structured flags to help trace classification quality.
        """
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
        """
        Full diagnostic dictionary suitable for export or review.
        """
        return {
            "sample_id": getattr(self, "sample_id", "unknown"),
            "vendor_name": getattr(self, "vendor_name", "unknown"),
            "family": getattr(self, "family", "unknown"),
            "confidence": round(getattr(self, "confidence_score", 0.0), 4),
            "signal_score": self.signal_score,
            "flags": ";".join(self.get_diagnostic_flags())
        }
