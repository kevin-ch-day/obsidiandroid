"""Legacy shim: feature enrichment stage lives under ``obsidiandroid.pipeline.stage_feature_enrichment``."""

from __future__ import annotations

import importlib
import sys

_mod = importlib.import_module("obsidiandroid.pipeline.stage_feature_enrichment")
sys.modules[__name__] = _mod
