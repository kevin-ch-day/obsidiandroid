"""Legacy shim: implementation lives under obsidiandroid.database.db_av_engine_detection_totals."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.db_av_engine_detection_totals")
sys.modules[__name__] = _mod

