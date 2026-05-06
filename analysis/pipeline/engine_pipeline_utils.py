"""Legacy shim: lives under ``obsidiandroid.pipeline.engine_pipeline_utils``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.engine_pipeline_utils")
sys.modules[__name__] = _mod
