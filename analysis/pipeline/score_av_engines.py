"""Legacy shim: lives under ``obsidiandroid.pipeline.score_av_engines``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.score_av_engines")
sys.modules[__name__] = _mod
