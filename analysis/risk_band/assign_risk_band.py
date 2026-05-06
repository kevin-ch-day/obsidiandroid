"""Legacy shim: implementation lives under ``obsidiandroid.risk_band.assign_risk_band``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.risk_band.assign_risk_band")
sys.modules[__name__] = _mod
