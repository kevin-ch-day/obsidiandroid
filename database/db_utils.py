"""Legacy shim: DB utility helpers live under ``obsidiandroid.database.db_utils``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.db_utils")
sys.modules[__name__] = _mod
