"""Legacy shim for ``ml_classification.ml_utils.accuracy_band_utils``.

Canonical implementation lives at ``obsidiandroid.evaluation.accuracy_band_utils``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.evaluation.accuracy_band_utils")
sys.modules[__name__] = _mod
