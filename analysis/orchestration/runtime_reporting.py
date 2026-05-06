"""Legacy shim: implementation lives under ``obsidiandroid.orchestration.runtime_reporting``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.orchestration.runtime_reporting")
sys.modules[__name__] = _mod
