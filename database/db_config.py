"""Legacy shim: connection constants live under ``obsidiandroid.database.db_config``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.db_config")
sys.modules[__name__] = _mod
