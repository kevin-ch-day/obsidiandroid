"""Legacy shim: MySQL error helpers live under ``obsidiandroid.database.db_errors``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.db_errors")
sys.modules[__name__] = _mod
