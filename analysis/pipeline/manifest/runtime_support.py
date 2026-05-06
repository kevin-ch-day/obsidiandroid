"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.manifest.runtime_support``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.manifest.runtime_support")
sys.modules[__name__] = _mod
