"""Legacy shim: implementation lives under ``obsidiandroid.governance.policy``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.governance.policy")
sys.modules[__name__] = _mod
