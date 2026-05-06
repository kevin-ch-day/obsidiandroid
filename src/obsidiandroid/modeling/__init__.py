"""ML modeling helpers and thin canonical aliases.

Pass 47 exposed a minimal, docs-approved alias set backed by identity-preserving
module objects. Subsequent passes physically moved orchestration-heavy training
controllers and utility helpers while keeping legacy shims:

- :mod:`obsidiandroid.modeling.pipeline_core` (physical)
- :mod:`obsidiandroid.modeling.model_trainer_factory` (physical)
- :mod:`obsidiandroid.modeling.data_alignment` (physical)
- :mod:`obsidiandroid.modeling.distribution_reporter` (physical)
- :mod:`obsidiandroid.modeling.feature_label_alignment_helper` (physical)
- :mod:`obsidiandroid.modeling.ml_result_analyzer` (physical)
- :mod:`obsidiandroid.modeling.ml_result_validator` (physical)
- :mod:`obsidiandroid.modeling.model_prediction` (physical)

See :mod:`obsidiandroid.modeling.model_exporter` for persisted model artifacts.

Physical training-stack helpers (**Pass 93**) load lazily via :func:`__getattr__`:
``pipeline_result_promoter``, ``train_model_executor``, ``model_training``,
``prediction_builder``, ``model_evaluation``, ``training_helpers``, and the
``ml_trainers`` subpackage.
"""

from __future__ import annotations

import importlib
import sys

_LAZY_PHYSICAL_SUBMODULES = frozenset(
    {
        "pipeline_result_promoter",
        "train_model_executor",
        "model_training",
        "prediction_builder",
        "model_evaluation",
        "training_helpers",
    }
)


def __getattr__(name: str):
    """Resolve optional physical modeling submodules without eager importing."""
    if name in _LAZY_PHYSICAL_SUBMODULES:
        module = importlib.import_module(f"obsidiandroid.modeling.{name}")
        globals()[name] = module
        return module
    if name == "ml_trainers":
        module = importlib.import_module("obsidiandroid.modeling.ml_trainers")
        globals()[name] = module
        return module
    message = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(message)


def __dir__():
    names = sorted(set(globals()) | set(__all__))
    return names


_CANONICAL_SUBMODULE_NAMES = (
    "data_alignment",
    "distribution_reporter",
    "feature_label_alignment_helper",
    "ml_result_analyzer",
    "ml_result_validator",
    "model_prediction",
    "model_trainer_factory",
    "pipeline_core",
)

_LEGACY_BY_CANONICAL = {
    "data_alignment": "obsidiandroid.modeling.data_alignment",
    "distribution_reporter": "obsidiandroid.modeling.distribution_reporter",
    "feature_label_alignment_helper": "obsidiandroid.modeling.feature_label_alignment_helper",
    "ml_result_analyzer": "obsidiandroid.modeling.ml_result_analyzer",
    "ml_result_validator": "obsidiandroid.modeling.ml_result_validator",
    "model_prediction": "obsidiandroid.modeling.model_prediction",
    "model_trainer_factory": "obsidiandroid.modeling.model_trainer_factory",
    "pipeline_core": "obsidiandroid.modeling.pipeline_core",
}

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(_LEGACY_BY_CANONICAL[_name])
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.modeling.{_name}", _canon)

__all__ = [
    "model_exporter",
    *_CANONICAL_SUBMODULE_NAMES,
    *_LAZY_PHYSICAL_SUBMODULES,
    "ml_trainers",
]

del _CANONICAL_SUBMODULE_NAMES, _LEGACY_BY_CANONICAL, _name, _canon
