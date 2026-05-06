"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.artifacts.registry``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.artifacts.registry")
sys.modules[__name__] = _mod
