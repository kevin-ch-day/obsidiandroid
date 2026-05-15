"""Legacy shim: cohort SQL fragments live under ``obsidiandroid.database.cohort_sql_fragments``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.database.cohort_sql_fragments", __name__)
sys.modules[__name__] = _mod
