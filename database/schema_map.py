"""Legacy shim: schema map lives under ``obsidiandroid.database.schema_map``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.schema_map")
sys.modules[__name__] = _mod
