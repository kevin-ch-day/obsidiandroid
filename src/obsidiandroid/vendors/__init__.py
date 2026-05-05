"""Vendor parsing canonical aliases (Pass 51 first slice).

Implementation remains under ``analysis.vendor_processing`` for now. This package
exposes only the docs-approved parser-map module as the canonical import surface.
"""

from __future__ import annotations

import importlib
import sys

_CANONICAL_SUBMODULE_NAMES = ("vendor_parser_map",)
_LEGACY_BY_CANONICAL = {
    "vendor_parser_map": "analysis.vendor_processing.vendor_parser_map",
}

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(_LEGACY_BY_CANONICAL[_name])
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.vendors.{_name}", _canon)

__all__ = list(_CANONICAL_SUBMODULE_NAMES)

del _CANONICAL_SUBMODULE_NAMES, _LEGACY_BY_CANONICAL, _name, _canon
