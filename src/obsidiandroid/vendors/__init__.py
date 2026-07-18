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

import sys

from obsidiandroid.vendors.contracts.parsed_label_metadata import ParsedLabelMetadata  # noqa: F401
from obsidiandroid.vendors.contracts.record_core import VendorClassificationRecord  # noqa: F401
from obsidiandroid.vendors.parsing.generic_label_parser import parse_generic_classification  # noqa: F401
from obsidiandroid.vendors.parsing import vendor_parser_map

sys.modules.setdefault("obsidiandroid.vendors.vendor_parser_map", vendor_parser_map)

__all__ = ["vendor_parser_map"]

# Stable contract re-exports (so callers don't need to reach into contracts.*).
__all__.extend(
    [
        "ParsedLabelMetadata",
        "VendorClassificationRecord",
        "parse_generic_classification",
    ]
)
