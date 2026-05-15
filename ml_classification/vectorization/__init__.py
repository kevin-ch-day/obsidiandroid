"""Legacy ``ml_classification.vectorization`` package shim.

Canonical implementations live under ``obsidiandroid.features.vectorization``.
"""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim
from obsidiandroid.modeling.ml_classification_shim_facades import (
    ML_CLASSIFICATION_VECTORIZATION_SUBMODULES,
)

for _name in sorted(ML_CLASSIFICATION_VECTORIZATION_SUBMODULES):
    _canonical = f"obsidiandroid.features.vectorization.{_name}"
    _mod = import_legacy_shim(_canonical, f"{__name__}.{_name}", warn=True)
    globals()[_name] = _mod
    sys.modules[f"{__name__}.{_name}"] = _mod


def __dir__() -> list[str]:
    return sorted(ML_CLASSIFICATION_VECTORIZATION_SUBMODULES)


__all__ = tuple(sorted(ML_CLASSIFICATION_VECTORIZATION_SUBMODULES))
