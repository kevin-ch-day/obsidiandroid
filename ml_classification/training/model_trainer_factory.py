"""Legacy shim for ``ml_classification.training.model_trainer_factory``.

Canonical implementation lives at ``obsidiandroid.modeling.model_trainer_factory``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.modeling.model_trainer_factory")
sys.modules[__name__] = _mod
