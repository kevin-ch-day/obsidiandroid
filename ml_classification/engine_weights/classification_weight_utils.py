"""Legacy shim for ``ml_classification.engine_weights.classification_weight_utils``.

Canonical implementation lives at ``obsidiandroid.engine_weights.classification_weight_utils``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.engine_weights.classification_weight_utils")
sys.modules[__name__] = _mod
