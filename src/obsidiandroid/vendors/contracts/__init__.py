"""Vendor record + parsed-metadata contracts.

Previously (Pass 60) vendor parsing/record contracts lived under the removed
``model.parsing`` / ``model.vendor`` shim tree; implementations are here under
``obsidiandroid.vendors.contracts``.

This package is intentionally *implementation-backed* for now (no behavior changes).
"""

from __future__ import annotations

from .metadata_normalizer import ParsedMetadataNormalizer
from .parsed_label_metadata import ParsedLabelMetadata
from .record_diagnostics import RecordDiagnosticsMixin
from .record_core import VendorClassificationRecord

__all__ = [
    "ParsedMetadataNormalizer",
    "ParsedLabelMetadata",
    "RecordDiagnosticsMixin",
    "VendorClassificationRecord",
]
