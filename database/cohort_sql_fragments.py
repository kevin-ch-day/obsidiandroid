"""Legacy shim: cohort SQL fragments live under ``obsidiandroid.database.cohort_sql_fragments``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.cohort_sql_fragments")
sys.modules[__name__] = _mod
