"""ML modeling helpers and thin canonical aliases.

Pass 47 exposes a minimal, docs-approved alias set backed by
``ml_classification.*`` module objects (identity-preserving):

- :mod:`obsidiandroid.modeling.pipeline_core`
- :mod:`obsidiandroid.modeling.model_trainer_factory`
- :mod:`obsidiandroid.modeling.distribution_reporter`
- :mod:`obsidiandroid.modeling.feature_label_alignment_helper`

See :mod:`obsidiandroid.modeling.model_exporter` for persisted model artifacts.
"""

from __future__ import annotations

import importlib
import sys

_CANONICAL_SUBMODULE_NAMES = (
    "distribution_reporter",
    "feature_label_alignment_helper",
    "model_trainer_factory",
    "pipeline_core",
)

_LEGACY_BY_CANONICAL = {
    "distribution_reporter": "ml_classification.ml_utils.distribution_reporter",
    "feature_label_alignment_helper": "ml_classification.ml_utils.feature_label_alignment_helper",
    "model_trainer_factory": "ml_classification.training.model_trainer_factory",
    "pipeline_core": "ml_classification.training.pipeline_core",
}

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(_LEGACY_BY_CANONICAL[_name])
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.modeling.{_name}", _canon)

__all__ = ["model_exporter", *_CANONICAL_SUBMODULE_NAMES]

del _CANONICAL_SUBMODULE_NAMES, _LEGACY_BY_CANONICAL, _name, _canon
