"""Legacy shim: implementation lives under obsidiandroid.database.db_extract_av_label_keywords."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.database.db_extract_av_label_keywords")
sys.modules[__name__] = _mod
