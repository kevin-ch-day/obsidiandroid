"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.permission_trends.sample_permission_data``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.permission_trends.sample_permission_data")
sys.modules[__name__] = _mod
