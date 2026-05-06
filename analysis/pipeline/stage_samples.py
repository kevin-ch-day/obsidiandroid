"""Legacy shim: samples stage lives under ``obsidiandroid.pipeline.stage_samples``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.stage_samples")
sys.modules[__name__] = _mod
