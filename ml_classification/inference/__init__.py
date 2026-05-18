"""Legacy ``ml_classification.inference`` package shim."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim
from obsidiandroid.modeling.legacy_ml_classification_manifest import (
    ML_CLASSIFICATION_INFERENCE_SUBMODULES,
)

for _name in sorted(ML_CLASSIFICATION_INFERENCE_SUBMODULES):
    _canonical = f"obsidiandroid.inference.{_name}"
    _mod = import_legacy_shim(_canonical, f"{__name__}.{_name}", warn=True)
    globals()[_name] = _mod
    sys.modules[f"{__name__}.{_name}"] = _mod


def __dir__() -> list[str]:
    return sorted(ML_CLASSIFICATION_INFERENCE_SUBMODULES)


__all__ = tuple(sorted(ML_CLASSIFICATION_INFERENCE_SUBMODULES))
