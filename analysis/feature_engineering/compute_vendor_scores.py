"""Legacy shim: implementation lives under ``obsidiandroid.feature_engineering.compute_vendor_scores``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.feature_engineering.compute_vendor_scores")
sys.modules[__name__] = _mod
