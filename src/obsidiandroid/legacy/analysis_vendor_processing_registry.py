"""Legacy ``analysis.vendor_processing`` shim registry."""

from __future__ import annotations

import importlib
import sys

from obsidiandroid.vendors.parsing.vendor_parser_submodule_manifest import (
    VENDOR_PARSER_SUBMODULE_NAMES,
)

_LEGACY_PKG = "analysis.vendor_processing"
_CANON_PREFIX = "obsidiandroid.vendors.parsing"


def register_analysis_vendor_processing_legacy_aliases(package: object | None = None) -> None:
    for name in VENDOR_PARSER_SUBMODULE_NAMES:
        canon_name = f"{_CANON_PREFIX}.{name}"
        mod = importlib.import_module(canon_name)
        sys.modules.setdefault(f"{_LEGACY_PKG}.{name}", mod)
        if package is not None:
            setattr(package, name, mod)


__all__ = ("VENDOR_PARSER_SUBMODULE_NAMES", "register_analysis_vendor_processing_legacy_aliases")
