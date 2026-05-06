"""Legacy shim for ``ml_classification.engine_weights.engine_weights_utils``.

Canonical implementation lives at ``obsidiandroid.engine_weights.engine_weights_utils``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.engine_weights.engine_weights_utils")
sys.modules[__name__] = _mod
