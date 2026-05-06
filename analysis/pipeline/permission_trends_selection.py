"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.permission_trends_selection``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.permission_trends_selection")
sys.modules[__name__] = _mod
