"""Legacy shim for ``ml_classification.training.feature_schema_audit``.

Canonical implementation lives at ``obsidiandroid.features.feature_schema_audit``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.features.feature_schema_audit")
sys.modules[__name__] = _mod
