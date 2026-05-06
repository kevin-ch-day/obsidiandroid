"""Legacy shim for ``ml_classification.engine_weights.assign_detection_tiers``.

Canonical implementation lives at ``obsidiandroid.engine_weights.assign_detection_tiers``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.engine_weights.assign_detection_tiers")
sys.modules[__name__] = _mod
