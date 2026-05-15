"""Legacy shim: implementation lives under ``obsidiandroid.risk_band``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.risk_band", __name__, warn=True)
sys.modules[__name__] = _mod
