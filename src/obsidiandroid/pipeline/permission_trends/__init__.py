"""Permission-trends pipeline helpers."""

from __future__ import annotations

import importlib

from .permission_trends_submodule_manifest import PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES

for _name in PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES:
    _canon = importlib.import_module(f"obsidiandroid.pipeline.permission_trends.{_name}")
    globals()[_name] = _canon

__all__ = list(PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES)

del _name, _canon
