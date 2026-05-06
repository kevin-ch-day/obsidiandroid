"""Legacy shim for ``ml_classification.training.train_model_executor``.

Canonical implementation lives at ``obsidiandroid.modeling.train_model_executor``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.modeling.train_model_executor")
sys.modules[__name__] = _mod
