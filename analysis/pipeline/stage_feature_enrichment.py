"""Legacy shim: feature enrichment stage lives under ``obsidiandroid.pipeline.stage_feature_enrichment``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.pipeline.stage_feature_enrichment", __name__)
sys.modules[__name__] = _mod
