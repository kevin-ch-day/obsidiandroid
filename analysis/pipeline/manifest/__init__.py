"""Legacy shim: manifest helpers live under ``obsidiandroid.pipeline.manifest``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim
from obsidiandroid.legacy.analysis_pipeline_manifest_registry import (
    LEGACY_EXPORT_NAMES,
    register_analysis_pipeline_manifest_legacy_aliases,
)

_mod = import_legacy_shim("obsidiandroid.pipeline.manifest", __name__)
register_analysis_pipeline_manifest_legacy_aliases(_mod)
sys.modules[__name__] = _mod

__all__ = list(LEGACY_EXPORT_NAMES)
