"""Legacy ``ml_classification.engine_weights`` package shim."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim
from obsidiandroid.modeling.ml_classification_shim_facades import (
    ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES,
)

for _name in sorted(ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES):
    _canonical = f"obsidiandroid.engine_weights.{_name}"
    _mod = import_legacy_shim(_canonical, f"{__name__}.{_name}")
    globals()[_name] = _mod
    sys.modules[f"{__name__}.{_name}"] = _mod


def __dir__() -> list[str]:
    return sorted(ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES)


__all__ = tuple(sorted(ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES))
