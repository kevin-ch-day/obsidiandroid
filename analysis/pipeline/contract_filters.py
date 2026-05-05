"""Legacy shim: cohort contract filters implementation lives under ``obsidiandroid.pipeline``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.contract_filters")
sys.modules[__name__] = _mod
