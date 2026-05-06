"""Legacy shim: pipeline runner implementation lives under ``obsidiandroid.pipeline.runner``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.runner")
sys.modules[__name__] = _mod
