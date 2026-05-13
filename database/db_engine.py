"""Legacy shim: MySQL engine lives under ``obsidiandroid.database.db_engine``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.db_engine")
sys.modules[__name__] = _mod
