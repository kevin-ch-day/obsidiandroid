"""Legacy ``ml_classification.labeling`` (shim-only).

Canonical implementations live under ``obsidiandroid.labeling``.
Prefer ``obsidiandroid.labeling.taxonomy`` for public taxonomy helpers.

Submodule names are defined in :mod:`obsidiandroid.modeling.ml_classification_shim_facades`.
"""

from __future__ import annotations

from typing import Any

from obsidiandroid.modeling.ml_classification_shim_facades import (
    ML_CLASSIFICATION_LABELING_SUBMODULES,
    lazy_legacy_submodule,
)


def __getattr__(name: str) -> Any:
    return lazy_legacy_submodule(name, __name__, ML_CLASSIFICATION_LABELING_SUBMODULES)


def __dir__() -> list[str]:
    return sorted(ML_CLASSIFICATION_LABELING_SUBMODULES)


__all__ = tuple(sorted(ML_CLASSIFICATION_LABELING_SUBMODULES))
