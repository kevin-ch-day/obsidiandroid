"""Legacy ``ml_classification.engine_weights`` (shim-only).

Canonical implementations live under ``obsidiandroid.engine_weights``.
Submodule names are defined in :mod:`obsidiandroid.modeling.ml_classification_shim_facades`.
"""

from __future__ import annotations

from typing import Any

from obsidiandroid.legacy_shim_lazy import lazy_legacy_submodule
from obsidiandroid.modeling.ml_classification_shim_facades import (
    ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES,
)


def __getattr__(name: str) -> Any:
    return lazy_legacy_submodule(name, __name__, ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES)


def __dir__() -> list[str]:
    return sorted(ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES)


__all__ = tuple(sorted(ML_CLASSIFICATION_ENGINE_WEIGHTS_SUBMODULES))
