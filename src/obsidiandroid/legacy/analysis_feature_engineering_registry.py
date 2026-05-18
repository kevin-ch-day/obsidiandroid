"""Legacy ``analysis.feature_engineering`` shim registry."""

from __future__ import annotations

import importlib
import sys

FEATURE_ENGINEERING_LEGACY_SHIM_MODULE_STEMS: tuple[str, ...] = (
    "assign_tier_scores",
    "compute_vendor_scores",
    "pattern_analysis",
    "prepare_engine_metrics",
)

LEGACY_EXPORT_NAMES: tuple[str, ...] = FEATURE_ENGINEERING_LEGACY_SHIM_MODULE_STEMS


def register_analysis_feature_engineering_legacy_aliases(package: object | None = None) -> None:
    for name in LEGACY_EXPORT_NAMES:
        mod = importlib.import_module(f"obsidiandroid.feature_engineering.{name}")
        sys.modules.setdefault(f"analysis.feature_engineering.{name}", mod)
        if package is not None:
            setattr(package, name, mod)


__all__ = (
    "FEATURE_ENGINEERING_LEGACY_SHIM_MODULE_STEMS",
    "LEGACY_EXPORT_NAMES",
    "register_analysis_feature_engineering_legacy_aliases",
)
