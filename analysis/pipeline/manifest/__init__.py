"""Legacy shim: manifest helpers live under ``obsidiandroid.pipeline.manifest``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.pipeline.manifest", __name__)
sys.modules[__name__] = _mod
