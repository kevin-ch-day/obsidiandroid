"""Legacy shim for ``ml_classification.training.model_evaluation``.

Canonical implementation lives at ``obsidiandroid.modeling.model_evaluation``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.modeling.model_evaluation")
sys.modules[__name__] = _mod
