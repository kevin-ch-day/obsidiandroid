"""Legacy shim for ``ml_classification.inference.signal_health_checker``.

Canonical implementation lives at ``obsidiandroid.inference.signal_health_checker``.
"""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.inference.signal_health_checker")
sys.modules[__name__] = _mod
