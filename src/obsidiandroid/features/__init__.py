"""Feature-engineering canonical aliases (Pass 47 minimal slice).

**Pass 83:** Vectorization implementations live under ``obsidiandroid.features.vectorization``
(physical). ``ml_classification.vectorization.*`` are identity shims (**Pass 82** façade
entries still re-export the same module objects via ``sys.modules``).

See ``docs/ML_BOUNDARY_PLAN.md``.
"""

from __future__ import annotations

import importlib
import sys

from .features_facade_manifest import FEATURES_FACADE_ALIAS_TARGETS

for _name, _canon_qual in FEATURES_FACADE_ALIAS_TARGETS:
    _canon = importlib.import_module(_canon_qual)
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.features.{_name}", _canon)

__all__ = [name for name, _ in FEATURES_FACADE_ALIAS_TARGETS]

del _name, _canon_qual, _canon
