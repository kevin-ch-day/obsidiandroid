"""Legacy shim: artifact helpers live under ``obsidiandroid.pipeline.artifacts``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.artifacts")
sys.modules[__name__] = _mod
