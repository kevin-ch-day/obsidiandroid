"""Legacy shim: modeling stage lives under ``obsidiandroid.pipeline.stage_modeling``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.stage_modeling")
sys.modules[__name__] = _mod
