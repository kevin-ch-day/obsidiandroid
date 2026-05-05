"""Legacy shim for ``model.vendor``.

Pass 60 physically moved vendor record modules to ``obsidiandroid.vendors.contracts``.

This package preserves legacy import compatibility and ModuleType identity.
"""

from __future__ import annotations

import importlib
import sys

_SUBMODULES = (
    "feature_engine",
    "record_core",
    "record_builder",
    "record_validator",
)

for _name in _SUBMODULES:
    _mod = importlib.import_module(f"obsidiandroid.vendors.contracts.{_name}")
    globals()[_name] = _mod
    sys.modules.setdefault(f"model.vendor.{_name}", _mod)

VendorClassificationRecord = record_core.VendorClassificationRecord

__all__ = [
    "VendorClassificationRecord",
    *_SUBMODULES,
]

del _SUBMODULES, _name, _mod
