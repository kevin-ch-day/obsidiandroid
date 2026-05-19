"""Permission-trends pipeline helpers (canonical **Pass 74**).

Legacy ``analysis.pipeline.permission_trends.*`` resolves to the same module
objects via compatibility aliases brokered by the protected
``analysis.pipeline`` shell.
"""

from __future__ import annotations

import importlib
import sys

from .permission_trends_submodule_manifest import PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES

for _name in PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES:
    _canon = importlib.import_module(f"obsidiandroid.pipeline.permission_trends.{_name}")
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.pipeline.permission_trends.{_name}", _canon)

__all__ = list(PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES)

del _name, _canon
