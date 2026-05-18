"""Vendor scoring, tiering, and exploratory feature helpers.

Implementation is canonical here (**Pass 78**); ``analysis.feature_engineering`` is an
identity shim to this package and its submodules (same :class:`types.ModuleType` objects).
"""

from __future__ import annotations

from .assign_tier_scores import assign_tier_scores
from .compute_vendor_scores import run_score_analysis
from .feature_engineering_import_surface import FEATURE_ENGINEERING_LEGACY_SHIM_MODULE_STEMS
from .pattern_analysis import (
    compute_pca_features,
    detect_outliers,
    feature_correlation_summary,
)
from .prepare_engine_metrics import prepare_engine_metrics_for_ml

__all__ = [
    "assign_tier_scores",
    "run_score_analysis",
    "prepare_engine_metrics_for_ml",
    "feature_correlation_summary",
    "detect_outliers",
    "compute_pca_features",
]
