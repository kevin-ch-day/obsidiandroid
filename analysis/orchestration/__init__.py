"""Legacy shim: implementation lives under ``obsidiandroid.orchestration``."""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim
from obsidiandroid.legacy.analysis_orchestration_registry import (
    LEGACY_EXPORT_NAMES,
    register_analysis_orchestration_legacy_aliases,
)

_mod = import_legacy_shim("obsidiandroid.orchestration", __name__, warn=True)
register_analysis_orchestration_legacy_aliases(_mod)
sys.modules[__name__] = _mod

__all__ = list(LEGACY_EXPORT_NAMES)
