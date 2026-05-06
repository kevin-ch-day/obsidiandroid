"""Legacy shim for ``ml_classification.engine_weights.build_classification_weights``.

Canonical implementation lives at ``obsidiandroid.engine_weights.build_classification_weights``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.engine_weights.build_classification_weights")
sys.modules[__name__] = _mod
