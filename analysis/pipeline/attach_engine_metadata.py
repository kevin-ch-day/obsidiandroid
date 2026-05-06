"""Legacy shim: lives under ``obsidiandroid.pipeline.attach_engine_metadata``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.attach_engine_metadata")
sys.modules[__name__] = _mod
