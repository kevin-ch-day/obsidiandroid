"""Legacy shim: ablation stage lives under ``obsidiandroid.pipeline.stage_ablation``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.stage_ablation")
sys.modules[__name__] = _mod
