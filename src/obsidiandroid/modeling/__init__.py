"""ML modeling helpers and thin canonical aliases.

Pass 47 exposed a minimal, docs-approved alias set backed by identity-preserving
module objects. Pass 87 physically moved the small ML utility helpers while keeping
legacy shims:

- :mod:`obsidiandroid.modeling.pipeline_core`
- :mod:`obsidiandroid.modeling.model_trainer_factory`
- :mod:`obsidiandroid.modeling.data_alignment` (physical)
- :mod:`obsidiandroid.modeling.distribution_reporter` (physical)
- :mod:`obsidiandroid.modeling.feature_label_alignment_helper` (physical)
- :mod:`obsidiandroid.modeling.ml_result_analyzer` (physical)
- :mod:`obsidiandroid.modeling.ml_result_validator` (physical)
- :mod:`obsidiandroid.modeling.model_prediction` (physical)

See :mod:`obsidiandroid.modeling.model_exporter` for persisted model artifacts.
"""

from __future__ import annotations

import importlib
import sys

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
    "model_trainer_factory": "ml_classification.training.model_trainer_factory",
    "pipeline_core": "ml_classification.training.pipeline_core",
}

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(_LEGACY_BY_CANONICAL[_name])
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.modeling.{_name}", _canon)

__all__ = ["model_exporter", *_CANONICAL_SUBMODULE_NAMES]

del _CANONICAL_SUBMODULE_NAMES, _LEGACY_BY_CANONICAL, _name, _canon
