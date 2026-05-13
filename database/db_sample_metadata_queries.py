"""Legacy shim: implementation lives under obsidiandroid.database.db_sample_metadata_queries."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.db_sample_metadata_queries")
sys.modules[__name__] = _mod

