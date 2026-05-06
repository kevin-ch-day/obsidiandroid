"""Legacy shim for ``ml_classification.engine_weights.classification_weight_inspector``.

Canonical implementation lives at ``obsidiandroid.engine_weights.classification_weight_inspector``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.engine_weights.classification_weight_inspector")
sys.modules[__name__] = _mod
