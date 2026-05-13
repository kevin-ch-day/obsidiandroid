# Filename: src/obsidiandroid/modeling/ml_classification_shim_facades.py
"""Submodule name sets for lazy ``ml_classification.*`` package facades (Pass 99+).

Keeps the allowed-name frozensets next to canonical modeling code so
``ml_classification.training`` / ``ml_classification.ml_utils`` ``__getattr__``
wrappers stay thin without duplicating lists in the repo-root shim tree.
"""

from __future__ import annotations

import importlib
from typing import Any

ML_CLASSIFICATION_TRAINING_SUBMODULES: frozenset[str] = frozenset(
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

ML_CLASSIFICATION_ML_UTILS_SUBMODULES: frozenset[str] = frozenset(
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


def lazy_legacy_submodule(name: str, legacy_pkg_qual: str, allowed: frozenset[str]) -> Any:
    """Resolve ``legacy_pkg_qual.<name>`` via importlib (thin leaf shims under ``ml_classification/``)."""
    if name not in allowed:
        raise AttributeError(f"module {legacy_pkg_qual!r} has no attribute {name!r}")
    return importlib.import_module(f"{legacy_pkg_qual}.{name}")


__all__ = (
    "ML_CLASSIFICATION_ML_UTILS_SUBMODULES",
    "ML_CLASSIFICATION_TRAINING_SUBMODULES",
    "lazy_legacy_submodule",
)
