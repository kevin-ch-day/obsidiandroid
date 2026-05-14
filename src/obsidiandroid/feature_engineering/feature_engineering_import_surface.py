# Filename: src/obsidiandroid/feature_engineering/feature_engineering_import_surface.py
"""Submodule stems registered for ``analysis.feature_engineering.*`` legacy shims (Pass 78).

``obsidiandroid.feature_engineering`` binds additional symbols on the package; this
tuple lists only the leaf modules mirrored under the legacy import root.
"""

from __future__ import annotations

FEATURE_ENGINEERING_LEGACY_SHIM_MODULE_STEMS: tuple[str, ...] = (
    "assign_tier_scores",
    "compute_vendor_scores",
    "pattern_analysis",
    "prepare_engine_metrics",
)

__all__ = ("FEATURE_ENGINEERING_LEGACY_SHIM_MODULE_STEMS",)
