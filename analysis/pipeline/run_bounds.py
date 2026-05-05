"""Legacy shim: run bounds helpers live under ``obsidiandroid.pipeline``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.run_bounds")
sys.modules[__name__] = _mod
