"""Canonical vendor parser package."""

from __future__ import annotations

import importlib
import sys

from obsidiandroid.vendors.parsing.vendor_parser_submodule_manifest import (
    VENDOR_PARSER_SUBMODULE_NAMES,
)

for _name in VENDOR_PARSER_SUBMODULE_NAMES:
    _mod = importlib.import_module(f"obsidiandroid.vendors.parsing.{_name}")
    globals()[_name] = _mod
    sys.modules.setdefault(f"obsidiandroid.vendors.parsing.{_name}", _mod)

__all__ = list(VENDOR_PARSER_SUBMODULE_NAMES)

del _name, _mod
