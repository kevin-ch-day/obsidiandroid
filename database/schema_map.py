"""Legacy shim: schema map lives under ``obsidiandroid.database.schema_map``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.database.schema_map", __name__)
sys.modules[__name__] = _mod
