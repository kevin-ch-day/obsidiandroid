"""Legacy shim: cohort export helpers live under ``obsidiandroid.pipeline.sample_exports``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.pipeline.sample_exports", __name__)
sys.modules[__name__] = _mod
