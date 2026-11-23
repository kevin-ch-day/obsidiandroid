# Filename: src/obsidiandroid/modeling/modeling_facade_manifest.py
"""Public :mod:`obsidiandroid.modeling` façade submodule names.

Used by :mod:`obsidiandroid.modeling` bootstrap and
:mod:`scripts.dev.check_import_surface` so ML façade wiring cannot drift between
package ``__init__`` and CI.
"""

from __future__ import annotations

# Retain the historical subset for callers of the manifest.
MODELING_FACADE_EAGER_SUBMODULE_NAMES: tuple[str, ...] = (
    "data_alignment",
    "distribution_reporter",
    "feature_label_alignment_helper",
    "ml_result_analyzer",
    "ml_result_validator",
    "model_prediction",
    "model_trainer_factory",
    "pipeline_core",
)

MODELING_FACADE_SUBMODULE_NAMES = (
    "model_exporter",
    *MODELING_FACADE_EAGER_SUBMODULE_NAMES,
    "dataset_splitter",
    "model_evaluation",
    "model_training",
    "pipeline_result_promoter",
    "prediction_builder",
    "train_model_executor",
    "training_helpers",
    "ml_trainers",
)

__all__ = (
    "MODELING_FACADE_EAGER_SUBMODULE_NAMES",
    "MODELING_FACADE_SUBMODULE_NAMES",
)
