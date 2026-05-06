"""Legacy shim for ``ml_classification.ml_utils.ml_eval_engine``.

Canonical implementation lives at ``obsidiandroid.evaluation.ml_eval_engine``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.evaluation.ml_eval_engine")
sys.modules[__name__] = _mod
