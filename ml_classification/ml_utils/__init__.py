"""Legacy ``ml_classification.ml_utils`` namespace (shim-only).

Concrete code lives under ``obsidiandroid.modeling.*`` and
``obsidiandroid.evaluation.*``. Submodules such as ``ml_eval_engine`` remain
addressable via ``import ml_classification.ml_utils.<name>`` or attribute
access on this package (:func:`__getattr__`).
"""

from __future__ import annotations

import importlib
from typing import Any

_SUBMODULE_NAMES = frozenset(
    {
        "accuracy_band_utils",
        "dataset_splitter",
        "distribution_reporter",
        "feature_alignment_utils",
        "feature_label_alignment_helper",
        "ml_comparator_summary",
        "ml_eval_engine",
        "ml_result_analyzer",
        "ml_result_validator",
    }
)


def __getattr__(name: str) -> Any:
    if name in _SUBMODULE_NAMES:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(_SUBMODULE_NAMES)


__all__ = tuple(sorted(_SUBMODULE_NAMES))
