"""Legacy ``analysis.execution`` shim registry."""

from __future__ import annotations

import importlib
import sys

_LEGACY_PKG = "analysis.execution"

_LEGACY_NAME_TO_CANON: dict[str, str] = {
    "av_parser_executor": "obsidiandroid.vendors.execution.av_parser_executor",
    "vendor_parser_runner": "obsidiandroid.vendors.execution.vendor_parser_runner",
    "vendor_record_factory": "obsidiandroid.vendors.execution.vendor_record_factory",
    "vendor_classification_processor": "obsidiandroid.vendors.execution.vendor_classification_processor",
}


def register_analysis_execution_legacy_aliases() -> None:
    for name, target in _LEGACY_NAME_TO_CANON.items():
        mod = importlib.import_module(target)
        sys.modules.setdefault(f"{_LEGACY_PKG}.{name}", mod)


LEGACY_EXPORT_NAMES: tuple[str, ...] = tuple(sorted(_LEGACY_NAME_TO_CANON.keys()))

__all__ = ("LEGACY_EXPORT_NAMES", "register_analysis_execution_legacy_aliases")
