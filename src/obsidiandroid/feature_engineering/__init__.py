"""Vendor scoring, tiering, and exploratory feature helpers.

Implementation is canonical here (**Pass 78**); ``analysis.feature_engineering`` is an
identity shim to this package and its submodules (same :class:`types.ModuleType` objects).
"""

from __future__ import annotations

import sys

from .assign_tier_scores import assign_tier_scores
from .compute_vendor_scores import run_score_analysis
from .prepare_engine_metrics import prepare_engine_metrics_for_ml
from .pattern_analysis import (
    compute_pca_features,
    detect_outliers,
    feature_correlation_summary,
)

__all__ = [
    "assign_tier_scores",
    "run_score_analysis",
    "prepare_engine_metrics_for_ml",
    "feature_correlation_summary",
    "detect_outliers",
    "compute_pca_features",
]

_LEGACY_FE_PREFIX = "analysis.feature_engineering."
for _name in ("assign_tier_scores", "compute_vendor_scores", "pattern_analysis", "prepare_engine_metrics"):
    sys.modules[_LEGACY_FE_PREFIX + _name] = sys.modules[__name__ + "." + _name]
