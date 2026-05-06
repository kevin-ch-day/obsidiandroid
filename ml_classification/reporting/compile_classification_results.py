"""Legacy shim for ``ml_classification.reporting.compile_classification_results``.

Canonical implementation lives at ``obsidiandroid.reporting.compile_classification_results``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.reporting.compile_classification_results")
sys.modules[__name__] = _mod
