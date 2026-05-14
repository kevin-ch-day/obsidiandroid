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
``prediction_builder``, ``model_evaluation``, ``training_helpers``, the
``ml_trainers`` subpackage, and (**Pass 94**) ``dataset_splitter``.
"""

from __future__ import annotations

import importlib
import sys

from .modeling_facade_manifest import MODELING_FACADE_EAGER_SUBMODULE_NAMES

_LAZY_PHYSICAL_SUBMODULES = frozenset(
    {
        "pipeline_result_promoter",
        "train_model_executor",
        "model_training",
        "prediction_builder",
        "model_evaluation",
        "training_helpers",
        "dataset_splitter",
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


for _name in MODELING_FACADE_EAGER_SUBMODULE_NAMES:
    _canon = importlib.import_module(f"{__name__}.{_name}")
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.modeling.{_name}", _canon)

__all__ = [
    "model_exporter",
    *MODELING_FACADE_EAGER_SUBMODULE_NAMES,
    *sorted(_LAZY_PHYSICAL_SUBMODULES),
    "ml_trainers",
]

del _name, _canon
