"""Legacy shim: ``main`` resolution helper lives under ``obsidiandroid.pipeline.main_facade``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.main_facade")
sys.modules[__name__] = _mod
