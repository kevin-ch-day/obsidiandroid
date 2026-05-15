"""Legacy shim: implementation lives under ``obsidiandroid.governance.policy``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.governance.policy", __name__)
sys.modules[__name__] = _mod
