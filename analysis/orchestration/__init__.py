"""Legacy shim: implementation lives under ``obsidiandroid.orchestration``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.orchestration")
sys.modules[__name__] = _mod
