"""Vendor scoring, tiering, and exploratory feature helpers."""

from __future__ import annotations

from .assign_tier_scores import assign_tier_scores
from .compute_vendor_scores import run_score_analysis
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
