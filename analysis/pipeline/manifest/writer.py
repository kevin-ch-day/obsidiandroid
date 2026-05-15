"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.manifest.writer``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.pipeline.manifest.writer", __name__)
sys.modules[__name__] = _mod
