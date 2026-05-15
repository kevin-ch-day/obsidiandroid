"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.artifacts.registry``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.pipeline.artifacts.registry", __name__)
sys.modules[__name__] = _mod
