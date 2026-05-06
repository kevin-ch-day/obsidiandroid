"""Legacy shim: implementation lives under ``obsidiandroid.governance.readiness``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.governance.readiness")
sys.modules[__name__] = _mod
