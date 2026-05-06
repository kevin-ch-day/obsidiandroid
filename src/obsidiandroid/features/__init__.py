"""Feature-engineering canonical aliases (Pass 47 minimal slice).

**Pass 83:** Vectorization implementations live under ``obsidiandroid.features.vectorization``
(physical). ``ml_classification.vectorization.*`` are identity shims (**Pass 82** façade
entries still re-export the same module objects via ``sys.modules``).

See ``docs/ML_BOUNDARY_PLAN.md``.
"""

from __future__ import annotations

import importlib
import sys

_CANONICAL_SUBMODULE_NAMES = (
    "feature_encoder",
    "feature_engine_selection",
    "feature_schema_audit",
    "feature_vector_builder",
    "feature_vendor_extractor",
)
_LEGACY_BY_CANONICAL = {
    "feature_encoder": "obsidiandroid.features.vectorization.feature_encoder",
    "feature_engine_selection": "obsidiandroid.features.vectorization.feature_engine_selection",
    "feature_schema_audit": "obsidiandroid.features.feature_schema_audit",
    "feature_vector_builder": "obsidiandroid.features.vectorization.feature_vector_builder",
    "feature_vendor_extractor": "obsidiandroid.features.vectorization.feature_vendor_extractor",
}

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(_LEGACY_BY_CANONICAL[_name])
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.features.{_name}", _canon)

__all__ = list(_CANONICAL_SUBMODULE_NAMES)

del _CANONICAL_SUBMODULE_NAMES, _LEGACY_BY_CANONICAL, _name, _canon
