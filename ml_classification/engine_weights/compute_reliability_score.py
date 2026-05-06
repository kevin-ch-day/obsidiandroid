"""Legacy shim for ``ml_classification.engine_weights.compute_reliability_score``.

Canonical implementation lives at ``obsidiandroid.engine_weights.compute_reliability_score``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.engine_weights.compute_reliability_score")
sys.modules[__name__] = _mod
