"""Legacy ``ml_classification.builder`` (shim-only).

Canonical implementations live under ``obsidiandroid.classification_builder``.
Submodule names are defined in :mod:`obsidiandroid.modeling.ml_classification_shim_facades`.
"""

from __future__ import annotations

from typing import Any

from obsidiandroid.legacy_shim_lazy import lazy_legacy_submodule
from obsidiandroid.modeling.ml_classification_shim_facades import (
    ML_CLASSIFICATION_BUILDER_SUBMODULES,
)


def __getattr__(name: str) -> Any:
    return lazy_legacy_submodule(name, __name__, ML_CLASSIFICATION_BUILDER_SUBMODULES)


def __dir__() -> list[str]:
    return sorted(ML_CLASSIFICATION_BUILDER_SUBMODULES)


__all__ = tuple(sorted(ML_CLASSIFICATION_BUILDER_SUBMODULES))
