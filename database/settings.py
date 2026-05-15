"""Legacy shim: structured DB settings live under ``obsidiandroid.database.settings``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.database.settings", __name__)
sys.modules[__name__] = _mod
