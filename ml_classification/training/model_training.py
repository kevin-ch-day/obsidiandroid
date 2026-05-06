"""Legacy shim for ``ml_classification.training.model_training``.

Canonical implementation lives at ``obsidiandroid.modeling.model_training``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.modeling.model_training")
sys.modules[__name__] = _mod
