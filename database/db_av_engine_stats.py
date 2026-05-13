"""Legacy shim: implementation lives under obsidiandroid.database.db_av_engine_stats."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.db_av_engine_stats")
sys.modules[__name__] = _mod
