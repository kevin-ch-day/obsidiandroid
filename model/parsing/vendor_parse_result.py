# Filename: model/vendor_parse_result.py
# Purpose : Encapsulates the result of parsing an AV vendor label, with signal evaluation utilities

from dataclasses import dataclass
from typing import Optional
from model.vendor.record_core import VendorClassificationRecord
from model.parsing.parsed_label_metadata import ParsedLabelMetadata


@dataclass
class VendorParseResult:
    record: Optional[VendorClassificationRecord]
    metadata: Optional[ParsedLabelMetadata]
    error: Optional[str] = None

    def was_successful(self) -> bool:
        return self.record is not None and self.error is None

    def has_metadata(self) -> bool:
        if not self.metadata:
            return False
        family = getattr(self.metadata, "family", "")
        return isinstance(family, str) and bool(family.strip())

    def is_trustworthy(self) -> bool:
        return (
            self.was_successful() and
            self.has_metadata() and
            self.metadata.confidence is not None and
            self.metadata.confidence >= 0.6
        )

    def is_high_signal(self) -> bool:
        if not (self.was_successful() and self.has_metadata()):
            return False

        high_conf_func = getattr(self.metadata, "is_high_confidence", None)
        is_high_conf = high_conf_func() if callable(high_conf_func) else False

        return (
            is_high_conf and
            self.is_android_target() and
            getattr(self.metadata, "is_valid", False)
        )

    def is_generic_result(self) -> bool:
        return self.has_metadata() and getattr(self.metadata, "is_generic_family", False)

    def is_android_target(self) -> bool:
        if not self.has_metadata():
            return False
        platform = getattr(self.metadata, "platform", None)
        return isinstance(platform, str) and platform.strip().lower() == "android"

    def signal_score(self) -> float:
        score_func = getattr(self.metadata, "signal_score", None)
        return score_func() if callable(score_func) else 0.0

    def summary(self) -> str:
        if not self.was_successful():
            vendor = self.record.vendor_name if self.record else 'N/A'
            return f"[FAIL] {vendor} → {self.error or 'Unknown error'}"

        vendor = self.record.vendor_name
        meta_summary = self.metadata.summary() if self.metadata else "No metadata"
        return f"[{vendor}] {meta_summary} (Signal Score: {self.signal_score():.3f})"

    def diagnostics(self) -> dict:
        return {
            "vendor": self.record.vendor_name if self.record else "unknown",
            "family": self.metadata.family if self.has_metadata() else "unknown",
            "success": self.was_successful(),
            "trustworthy": self.is_trustworthy(),
            "high_signal": self.is_high_signal(),
            "generic": self.is_generic_result(),
            "android": self.is_android_target(),
            "score": self.signal_score(),
            "error": self.error or "",
        }
