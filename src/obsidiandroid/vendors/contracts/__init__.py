"""Vendor record + parsed-metadata contracts.

Pass 60: physically moved legacy implementation modules from ``model.parsing`` and
``model.vendor`` into this canonical package while preserving legacy import
compatibility via ``model.parsing`` / ``model.vendor`` shim registration.

This package is intentionally *implementation-backed* for now (no behavior changes).
"""

from __future__ import annotations

from .parsed_label_metadata import ParsedLabelMetadata
from .record_core import VendorClassificationRecord

__all__ = [
    "ParsedLabelMetadata",
    "VendorClassificationRecord",
]
