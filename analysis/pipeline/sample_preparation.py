"""Legacy shim: sample preparation lives under ``obsidiandroid.pipeline.sample_preparation``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.sample_preparation")
sys.modules[__name__] = _mod
