"""Legacy shim: results warehouse stage lives under ``obsidiandroid.pipeline.stage_results_warehouse``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.stage_results_warehouse")
sys.modules[__name__] = _mod
