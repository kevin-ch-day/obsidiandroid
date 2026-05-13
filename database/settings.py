"""Legacy shim: structured DB settings live under ``obsidiandroid.database.settings``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.settings")
sys.modules[__name__] = _mod
