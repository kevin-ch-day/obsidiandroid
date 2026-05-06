"""Feature-engineering canonical aliases (Pass 47 minimal slice).

Reserved for feature matrix and vectorization; see ``docs/ML_BOUNDARY_PLAN.md``.
"""

from __future__ import annotations

import importlib
import sys

_CANONICAL_SUBMODULE_NAMES = ("feature_vector_builder",)
_LEGACY_BY_CANONICAL = {
    "feature_vector_builder": "ml_classification.vectorization.feature_vector_builder",
}

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(_LEGACY_BY_CANONICAL[_name])
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.features.{_name}", _canon)

__all__ = list(_CANONICAL_SUBMODULE_NAMES)

del _CANONICAL_SUBMODULE_NAMES, _LEGACY_BY_CANONICAL, _name, _canon
