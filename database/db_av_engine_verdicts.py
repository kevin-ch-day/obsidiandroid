"""Legacy shim: implementation lives under obsidiandroid.database.db_av_engine_verdicts."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.db_av_engine_verdicts")
sys.modules[__name__] = _mod

