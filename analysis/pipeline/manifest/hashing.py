"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.manifest.hashing``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.manifest.hashing")
sys.modules[__name__] = _mod
