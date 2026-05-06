"""Legacy shim for ``ml_classification.ml_utils.ml_comparator_summary``.

Canonical implementation lives at ``obsidiandroid.evaluation.ml_comparator_summary``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.evaluation.ml_comparator_summary")
sys.modules[__name__] = _mod
