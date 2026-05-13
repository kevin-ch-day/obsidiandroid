"""Legacy shim: implementation lives under obsidiandroid.database.db_fetch_av_engine_raw_results."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.db_fetch_av_engine_raw_results")
sys.modules[__name__] = _mod

