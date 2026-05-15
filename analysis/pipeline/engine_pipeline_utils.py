"""Legacy shim: lives under ``obsidiandroid.pipeline.engine_pipeline_utils``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.pipeline.engine_pipeline_utils", __name__)
sys.modules[__name__] = _mod
