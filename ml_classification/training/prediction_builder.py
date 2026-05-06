"""Legacy shim for ``ml_classification.training.prediction_builder``.

Canonical implementation lives at ``obsidiandroid.modeling.prediction_builder``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.modeling.prediction_builder")
sys.modules[__name__] = _mod
