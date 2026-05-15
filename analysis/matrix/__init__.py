"""Legacy shim: implementation lives under ``obsidiandroid.matrix``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.matrix", __name__, warn=True)
sys.modules[__name__] = _mod
