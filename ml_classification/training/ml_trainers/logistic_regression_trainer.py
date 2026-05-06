"""Legacy shim for ``ml_classification.training.ml_trainers.logistic_regression_trainer``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module(
    "obsidiandroid.modeling.ml_trainers.logistic_regression_trainer"
)
sys.modules[__name__] = _mod
