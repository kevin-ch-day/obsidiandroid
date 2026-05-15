"""Legacy shim: lives under ``obsidiandroid.pipeline.av_engine_pipeline``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.pipeline.av_engine_pipeline", __name__)
sys.modules[__name__] = _mod
