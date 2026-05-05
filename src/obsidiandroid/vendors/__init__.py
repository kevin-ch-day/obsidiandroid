"""Vendor parsing canonical surface.

Pass 59: parser implementations moved under ``obsidiandroid.vendors.parsing``.
This package keeps top-level compatibility for ``obsidiandroid.vendors.vendor_parser_map``.
"""

from __future__ import annotations

import importlib
import sys

_CANONICAL_SUBMODULE_NAMES = ("vendor_parser_map",)
_LEGACY_BY_CANONICAL = {
    "vendor_parser_map": "obsidiandroid.vendors.parsing.vendor_parser_map",
}

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(_LEGACY_BY_CANONICAL[_name])
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.vendors.{_name}", _canon)

__all__ = list(_CANONICAL_SUBMODULE_NAMES)

del _CANONICAL_SUBMODULE_NAMES, _LEGACY_BY_CANONICAL, _name, _canon
