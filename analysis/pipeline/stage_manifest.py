"""Legacy shim: manifest stage lives under ``obsidiandroid.pipeline.stage_manifest``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.stage_manifest")
sys.modules[__name__] = _mod
