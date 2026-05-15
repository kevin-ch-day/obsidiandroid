"""Legacy shim: run bounds helpers live under ``obsidiandroid.pipeline``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.pipeline.run_bounds", __name__)
sys.modules[__name__] = _mod
