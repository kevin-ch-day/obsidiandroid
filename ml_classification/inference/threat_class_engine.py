"""Legacy shim for ``ml_classification.inference.threat_class_engine``.

Canonical implementation lives at ``obsidiandroid.inference.threat_class_engine``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.inference.threat_class_engine")
sys.modules[__name__] = _mod
