"""Vendor domain canonical surface.

This package is the stable entrypoint for *public-ish* vendor APIs:

- Parser map access via :mod:`obsidiandroid.vendors.vendor_parser_map` (Pass 51/59).
- Vendor contracts (record + parsed-label metadata) via re-exported types.

Implementation details remain under subpackages:

- :mod:`obsidiandroid.vendors.parsing`
- :mod:`obsidiandroid.vendors.execution`
- :mod:`obsidiandroid.vendors.contracts`
"""

from __future__ import annotations

import importlib
import sys

from obsidiandroid.vendors.contracts.parsed_label_metadata import ParsedLabelMetadata
from obsidiandroid.vendors.contracts.record_core import VendorClassificationRecord
from obsidiandroid.vendors.parsing.generic_label_parser import parse_generic_classification

_CANONICAL_SUBMODULE_NAMES = ("vendor_parser_map",)
_LEGACY_BY_CANONICAL = {
    "vendor_parser_map": "obsidiandroid.vendors.parsing.vendor_parser_map",
}

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(_LEGACY_BY_CANONICAL[_name])
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.vendors.{_name}", _canon)

__all__ = list(_CANONICAL_SUBMODULE_NAMES)

# Stable contract re-exports (so callers don't need to reach into contracts.*).
__all__.extend(
    [
        "ParsedLabelMetadata",
        "VendorClassificationRecord",
        "parse_generic_classification",
    ]
)

del _CANONICAL_SUBMODULE_NAMES, _LEGACY_BY_CANONICAL, _name, _canon
