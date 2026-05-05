"""Pipeline artifact helper canonical aliases."""

from __future__ import annotations

import importlib
import sys

_CANONICAL_SUBMODULE_NAMES = ("paths", "registry")

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(f"analysis.pipeline.artifacts.{_name}")
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.pipeline.artifacts.{_name}", _canon)

__all__ = list(_CANONICAL_SUBMODULE_NAMES)

del _CANONICAL_SUBMODULE_NAMES, _name, _canon
