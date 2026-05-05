"""Permission-trends pipeline helper canonical aliases."""

from __future__ import annotations

import importlib
import sys

_CANONICAL_SUBMODULE_NAMES = (
    "bundle_manifest",
    "constants",
    "publish_paths",
    "reporting_support",
    "sample_permission_data",
    "stats_core",
)

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(f"analysis.pipeline.permission_trends.{_name}")
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.pipeline.permission_trends.{_name}", _canon)

__all__ = list(_CANONICAL_SUBMODULE_NAMES)

del _CANONICAL_SUBMODULE_NAMES, _name, _canon
