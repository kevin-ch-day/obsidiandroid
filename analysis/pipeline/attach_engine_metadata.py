"""Legacy shim: lives under ``obsidiandroid.pipeline.attach_engine_metadata``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.pipeline.attach_engine_metadata", __name__)
sys.modules[__name__] = _mod
