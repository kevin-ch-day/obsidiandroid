"""Legacy shim: modeling stage lives under ``obsidiandroid.pipeline.stage_modeling``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.pipeline.stage_modeling", __name__)
sys.modules[__name__] = _mod
