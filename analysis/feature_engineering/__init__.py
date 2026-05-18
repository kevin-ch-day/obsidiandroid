"""Legacy shim: implementation lives under ``obsidiandroid.feature_engineering``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim
from obsidiandroid.legacy.analysis_feature_engineering_registry import (
    LEGACY_EXPORT_NAMES,
    register_analysis_feature_engineering_legacy_aliases,
)

_mod = import_legacy_shim("obsidiandroid.feature_engineering", __name__, warn=True)
register_analysis_feature_engineering_legacy_aliases(_mod)
sys.modules[__name__] = _mod

__all__ = list(LEGACY_EXPORT_NAMES)
