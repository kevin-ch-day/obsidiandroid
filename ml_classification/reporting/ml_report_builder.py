"""Legacy shim for ``ml_classification.reporting.ml_report_builder``.

Canonical implementation lives at ``obsidiandroid.evaluation.ml_report_builder``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.evaluation.ml_report_builder")
sys.modules[__name__] = _mod
