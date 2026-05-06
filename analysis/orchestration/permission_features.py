"""Legacy shim: implementation lives under ``obsidiandroid.orchestration.permission_features``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.orchestration.permission_features")
sys.modules[__name__] = _mod
