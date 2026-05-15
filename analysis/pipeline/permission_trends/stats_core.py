"""Legacy shim: implementation lives under ``obsidiandroid.pipeline.permission_trends.stats_core``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.pipeline.permission_trends.stats_core", __name__)
sys.modules[__name__] = _mod
