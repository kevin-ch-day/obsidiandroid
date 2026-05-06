"""Legacy shim: lives under ``obsidiandroid.pipeline.vendor_metadata_pipeline``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.vendor_metadata_pipeline")
sys.modules[__name__] = _mod
