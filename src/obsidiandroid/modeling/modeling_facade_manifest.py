# Filename: src/obsidiandroid/modeling/modeling_facade_manifest.py
"""Eager :mod:`obsidiandroid.modeling` façade submodule names.

Used by :mod:`obsidiandroid.modeling` bootstrap and
:mod:`scripts.dev.check_import_surface` so ML façade wiring cannot drift between
package ``__init__`` and CI.
"""

from __future__ import annotations

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

# Import-surface parity: these eager façade names resolve through ``ml_classification.training``.
MODELING_FACADE_LEGACY_VIA_ML_CLASSIFICATION_TRAINING: frozenset[str] = frozenset(
    {"data_alignment", "model_prediction", "model_trainer_factory", "pipeline_core"}
)

__all__ = (
    "MODELING_FACADE_EAGER_SUBMODULE_NAMES",
    "MODELING_FACADE_LEGACY_VIA_ML_CLASSIFICATION_TRAINING",
)
