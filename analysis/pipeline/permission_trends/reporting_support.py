"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.permission_trends.reporting_support``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.permission_trends.reporting_support")
sys.modules[__name__] = _mod
