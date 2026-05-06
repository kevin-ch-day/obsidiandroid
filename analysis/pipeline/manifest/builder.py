"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.manifest.builder``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.manifest.builder")
sys.modules[__name__] = _mod
