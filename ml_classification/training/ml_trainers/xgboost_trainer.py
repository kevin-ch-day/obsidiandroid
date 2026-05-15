"""Legacy shim for ``ml_classification.training.ml_trainers.xgboost_trainer``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.modeling.ml_trainers.xgboost_trainer", __name__)
sys.modules[__name__] = _mod
