# Filename: model/vendor/record_core.py
# Description: Core dataclass structure for AV vendor classification records

from dataclasses import dataclass, field
from typing import List, Optional

from model.core.record_diagnostics import RecordDiagnosticsMixin
from model.parsing.parsed_label_metadata import ParsedLabelMetadata
from model.vendor.feature_engine import compute_all_features


@dataclass
class VendorClassificationRecord(RecordDiagnosticsMixin):
    """
    Represents a structured classification record for a single AV vendor label.
    Includes parsed fields, ML-friendly features, and diagnostic tags.
    """

    # --- Raw Input Fields ---
    sample_id: str
    vendor_name: str
    original_label: str

    # --- Normalized Parsed Fields ---
    family: str = "unknown"
    malware_type: str = "unknown"
    threat_class: str = "unknown"
    platform: str = "unknown"
    variant: str = "unknown"

    # --- Heuristic and Confidence Indicators ---
    is_known_family: bool = False
    is_generic_family: bool = False
    genericity_score: float = 0.0
    confidence_score: float = 0.0
    parser_quality: str = "unknown"
    signature_type: str = "pattern"
    confidence_reason: str = field(init=False, default="")

    # --- Derived ML Features ---
    composite_tag: str = field(init=False, default="")
    is_android: bool = field(init=False, default=False)
    is_valid: bool = field(init=False, default=False)
    family_match: bool = field(init=False, default=False)

    category_vector: List[str] = field(init=False, default_factory=list)
    threat_tags: List[str] = field(init=False, default_factory=list)
    signal_score: float = field(init=False, default=0.0)
    high_signal: bool = field(init=False, default=False)

    # --- Diagnostic Tracking ---
    edge_case_type: str = field(init=False, default="")
    diagnostic_tags: List[str] = field(init=False, default_factory=list)

    def __post_init__(self):
        self._validate_minimum_fields()
        self._compute_features_safely()

    def _validate_minimum_fields(self):
        if not self.sample_id or not self.original_label:
            self.edge_case_type = "missing_label"
        if not self.vendor_name:
            self.edge_case_type = "missing_vendor"

    def _compute_features_safely(self):
        try:
            compute_all_features(self)
        except Exception as e:
            self.is_valid = False
            self.edge_case_type = "feature_fail"
            self.diagnostic_tags.append(f"feature_error:{str(e)}")

    @classmethod
    def from_metadata(
        cls,
        sample_id: str,
        vendor_name: str,
        original_label: str,
        metadata: ParsedLabelMetadata,
        known_family: Optional[str]
    ) -> "VendorClassificationRecord":
        """
        Construct a record from parsed metadata and optionally validate against a known family.
        """
        if not metadata or not isinstance(metadata, ParsedLabelMetadata):
            raise ValueError("Invalid ParsedLabelMetadata provided.")

        normalized_family = (metadata.family or "unknown").strip().lower()
        expected_family = (known_family or "unknown").strip().lower()
        is_known = (normalized_family == expected_family and expected_family != "unknown")

        record = cls(
            sample_id=sample_id,
            vendor_name=vendor_name,
            original_label=original_label,
            family=normalized_family,
            malware_type=metadata.malware_type or "unknown",
            threat_class=metadata.threat_class or "unknown",
            platform=metadata.platform or "unknown",
            variant=metadata.variant or "unknown",
            is_known_family=is_known,
            is_generic_family=metadata.is_generic_family,
            genericity_score=metadata.signal_score(),
            confidence_score=metadata.confidence,
            parser_quality=metadata.parser_quality or "unknown",
            signature_type=metadata.signature_type or "pattern"
        )

        record.family_match = is_known
        return record

    @property
    def family_name(self) -> str:
        """
        Compatibility alias for accessing the normalized family name.
        """
        return self.family

    def to_dict(self) -> dict:
        return {
            "sample_id": self.sample_id,
            "vendor_name": self.vendor_name,
            "original_label": self.original_label,
            "family": self.family,
            "malware_type": self.malware_type,
            "threat_class": self.threat_class,
            "platform": self.platform,
            "variant": self.variant,
            "is_known_family": self.is_known_family,
            "is_generic_family": self.is_generic_family,
            "genericity_score": self.genericity_score,
            "confidence_score": self.confidence_score,
            "parser_quality": self.parser_quality,
            "signature_type": self.signature_type,
            "confidence_reason": self.confidence_reason,
            "composite_tag": self.composite_tag,
            "is_android": self.is_android,
            "is_valid": self.is_valid,
            "family_match": self.family_match,
            "category_vector": self.category_vector,
            "threat_tags": self.threat_tags,
            "signal_score": self.signal_score,
            "high_signal": self.high_signal,
            "edge_case_type": self.edge_case_type,
            "diagnostic_tags": self.diagnostic_tags
        }
