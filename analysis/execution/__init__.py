"""Legacy vendor execution package shim.

Implementation for vendor parser execution moved to
``obsidiandroid.vendors.execution``. This package preserves legacy
``analysis.execution.<name>`` import paths and module identity by registering
the canonical submodules in ``sys.modules`` at package import time.
"""

from __future__ import annotations

import importlib
import sys

_MOVED_SUBMODULES: dict[str, str] = {
    "av_parser_executor": "obsidiandroid.vendors.execution.av_parser_executor",
    "vendor_parser_runner": "obsidiandroid.vendors.execution.vendor_parser_runner",
    "vendor_record_factory": "obsidiandroid.vendors.execution.vendor_record_factory",
    "vendor_classification_processor": "obsidiandroid.vendors.execution.vendor_classification_processor",
}

for _name, _target in _MOVED_SUBMODULES.items():
    _mod = importlib.import_module(_target)
    sys.modules.setdefault(f"{__name__}.{_name}", _mod)

__all__ = sorted(_MOVED_SUBMODULES.keys())

del _MOVED_SUBMODULES, _name, _target, _mod

