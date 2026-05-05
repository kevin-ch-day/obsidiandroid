"""Legacy evaluation package shim.

Passes 61–62 physically moved a small set of evaluation helper modules to
``src/obsidiandroid/evaluation``. This package preserves legacy import
compatibility and ModuleType identity by registering the moved submodules in
``sys.modules`` at package import time, allowing direct imports like:

``import analysis.evaluation.model_tuning``

without keeping per-leaf shim files.
"""

from __future__ import annotations

import importlib
import sys

_MOVED_SUBMODULES: dict[str, str] = {
    "model_tuning": "obsidiandroid.evaluation.model_tuning",
    "random_forest_diagnostics": "obsidiandroid.evaluation.random_forest_diagnostics",
    "vendor_parser_matching": "obsidiandroid.evaluation.vendor_parser_matching",
    "vendor_classification_inspector": "obsidiandroid.evaluation.vendor_classification_inspector",
}

for _name, _target in _MOVED_SUBMODULES.items():
    _mod = importlib.import_module(_target)
    sys.modules.setdefault(f"{__name__}.{_name}", _mod)

__all__ = sorted(_MOVED_SUBMODULES.keys())

del _MOVED_SUBMODULES, _name, _target, _mod
