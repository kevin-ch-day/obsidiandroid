"""Legacy shim: implementation lives under ``obsidiandroid.feature_engineering.pattern_analysis``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.feature_engineering.pattern_analysis")
sys.modules[__name__] = _mod
