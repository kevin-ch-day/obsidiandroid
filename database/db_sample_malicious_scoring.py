"""Legacy shim: implementation lives under obsidiandroid.database.db_sample_malicious_scoring."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.db_sample_malicious_scoring")
sys.modules[__name__] = _mod

