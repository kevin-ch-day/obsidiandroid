"""Legacy ``ml_classification.training`` (shim-only).

Canonical implementations live under ``obsidiandroid.modeling`` (and nested
``ml_trainers``). Submodules remain importable via ``import ml_classification.training.<name>``
or :func:`__getattr__` on this package.
"""

from __future__ import annotations

import importlib
from typing import Any

_SUBMODULE_NAMES = frozenset(
    {
        "data_alignment",
        "feature_schema_audit",
        "model_evaluation",
        "model_prediction",
        "model_training",
        "model_trainer_factory",
        "pipeline_core",
        "pipeline_result_promoter",
        "prediction_builder",
        "train_model_executor",
        "training_helpers",
        "ml_trainers",
    }
)


def __getattr__(name: str) -> Any:
    if name in _SUBMODULE_NAMES:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(_SUBMODULE_NAMES)


__all__ = tuple(sorted(_SUBMODULE_NAMES))
