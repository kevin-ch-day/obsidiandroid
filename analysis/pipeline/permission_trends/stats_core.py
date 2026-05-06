"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.permission_trends.stats_core``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.permission_trends.stats_core")
sys.modules[__name__] = _mod
