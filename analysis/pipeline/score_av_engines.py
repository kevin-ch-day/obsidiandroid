"""Legacy shim: lives under ``obsidiandroid.pipeline.score_av_engines``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.pipeline.score_av_engines", __name__)
sys.modules[__name__] = _mod
