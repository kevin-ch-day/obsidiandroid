"""Legacy ``ml_classification.training`` (shim-only).

Canonical implementations live under ``obsidiandroid.modeling`` (and nested
``ml_trainers``). Submodule names are defined in
:mod:`obsidiandroid.modeling.legacy_ml_classification_manifest`.
"""

from __future__ import annotations

from typing import Any

from obsidiandroid.legacy_shim_lazy import lazy_legacy_submodule
from obsidiandroid.modeling.legacy_ml_classification_manifest import (
    ML_CLASSIFICATION_TRAINING_SUBMODULES,
)


def __getattr__(name: str) -> Any:
    return lazy_legacy_submodule(
        name,
        __name__,
        ML_CLASSIFICATION_TRAINING_SUBMODULES,
        canonical_pkg_qual="obsidiandroid.modeling",
        warn=True,
    )


def __dir__() -> list[str]:
    return sorted(ML_CLASSIFICATION_TRAINING_SUBMODULES)


__all__ = tuple(sorted(ML_CLASSIFICATION_TRAINING_SUBMODULES))
