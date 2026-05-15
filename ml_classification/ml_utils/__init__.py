"""Legacy ``ml_classification.ml_utils`` package shim."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim
from obsidiandroid.modeling.ml_classification_shim_facades import (
    ML_CLASSIFICATION_ML_UTILS_SUBMODULES,
)

_SUBMODULES = {
    "accuracy_band_utils": "obsidiandroid.evaluation.accuracy_band_utils",
    "dataset_splitter": "obsidiandroid.modeling.dataset_splitter",
    "distribution_reporter": "obsidiandroid.modeling.distribution_reporter",
    "feature_alignment_utils": "obsidiandroid.modeling.feature_alignment_utils",
    "feature_label_alignment_helper": "obsidiandroid.modeling.feature_label_alignment_helper",
    "ml_comparator_summary": "obsidiandroid.evaluation.ml_comparator_summary",
    "ml_eval_engine": "obsidiandroid.evaluation.ml_eval_engine",
    "ml_result_analyzer": "obsidiandroid.modeling.ml_result_analyzer",
    "ml_result_validator": "obsidiandroid.modeling.ml_result_validator",
}

for _name, _canonical in _SUBMODULES.items():
    _mod = import_legacy_shim(_canonical, f"{__name__}.{_name}")
    globals()[_name] = _mod
    sys.modules[f"{__name__}.{_name}"] = _mod


def __dir__() -> list[str]:
    return sorted(ML_CLASSIFICATION_ML_UTILS_SUBMODULES)


__all__ = tuple(sorted(ML_CLASSIFICATION_ML_UTILS_SUBMODULES))
