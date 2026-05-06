"""Legacy shim: implementation lives under ``obsidiandroid.governance.integrity``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.governance.integrity")
sys.modules[__name__] = _mod
