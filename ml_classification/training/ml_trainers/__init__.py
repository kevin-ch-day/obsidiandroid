"""Legacy ``ml_classification.training.ml_trainers`` (shim-only).

Canonical trainer modules live under ``obsidiandroid.modeling.ml_trainers``.
"""

from __future__ import annotations

import importlib
from typing import Any

_SUBMODULE_NAMES = frozenset(
    {
        "balanced_random_forest_trainer",
        "logistic_regression_trainer",
        "random_forest_trainer",
        "svm_trainer",
        "xgboost_trainer",
    }
)


def __getattr__(name: str) -> Any:
    if name in _SUBMODULE_NAMES:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(_SUBMODULE_NAMES)


__all__ = tuple(sorted(_SUBMODULE_NAMES))
