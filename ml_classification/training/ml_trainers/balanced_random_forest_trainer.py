"""Legacy shim for ``ml_classification.training.ml_trainers.balanced_random_forest_trainer``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module(
    "obsidiandroid.modeling.ml_trainers.balanced_random_forest_trainer"
)
sys.modules[__name__] = _mod
