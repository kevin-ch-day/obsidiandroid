"""Legacy shim: implementation lives under ``obsidiandroid.feature_engineering.prepare_engine_metrics``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.feature_engineering.prepare_engine_metrics")
sys.modules[__name__] = _mod
