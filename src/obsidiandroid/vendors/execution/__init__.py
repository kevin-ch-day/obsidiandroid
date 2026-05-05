"""Vendor execution helpers (parser runtime).

This package contains the implementation that executes vendor parsers over
AV verdict matrices to produce structured records and summaries.
"""

from __future__ import annotations

__all__ = [
    "av_parser_executor",
    "vendor_classification_processor",
    "vendor_parser_runner",
    "vendor_record_factory",
]

