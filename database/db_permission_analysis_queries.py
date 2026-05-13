"""Legacy shim: implementation lives under obsidiandroid.database.db_permission_analysis_queries."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.db_permission_analysis_queries")
sys.modules[__name__] = _mod

