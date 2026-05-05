"""Labeling canonical aliases (Pass 47 minimal slice)."""

from __future__ import annotations

import importlib
import sys

_CANONICAL_SUBMODULE_NAMES = ("classification_label_resolver",)
_LEGACY_BY_CANONICAL = {
    "classification_label_resolver": "ml_classification.labeling.classification_label_resolver",
}

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(_LEGACY_BY_CANONICAL[_name])
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.labeling.{_name}", _canon)

__all__ = list(_CANONICAL_SUBMODULE_NAMES)

del _CANONICAL_SUBMODULE_NAMES, _LEGACY_BY_CANONICAL, _name, _canon
"""Reserved for labeling utilities (see migration plan)."""
