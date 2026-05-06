"""Legacy shim: cohort export helpers live under ``obsidiandroid.pipeline.sample_exports``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.sample_exports")
sys.modules[__name__] = _mod
