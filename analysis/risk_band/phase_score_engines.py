"""Legacy shim: implementation lives under ``obsidiandroid.risk_band.phase_score_engines``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.risk_band.phase_score_engines")
sys.modules[__name__] = _mod
