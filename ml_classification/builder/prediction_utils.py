"""Legacy shim for ``ml_classification.builder.prediction_utils``.

Canonical implementation lives at ``obsidiandroid.classification_builder.prediction_utils``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.classification_builder.prediction_utils")
sys.modules[__name__] = _mod
