from .assign_tier_scores import assign_tier_scores
from .compute_vendor_scores import run_score_analysis
from .prepare_engine_metrics import prepare_engine_metrics_for_ml
from .pattern_analysis import (
    feature_correlation_summary,
    detect_outliers,
    compute_pca_features,
)

# Backward-compat alias (deprecated): use prepare_engine_metrics_for_ml.
quick_engine_prep = prepare_engine_metrics_for_ml

__all__ = [
    'assign_tier_scores',
    'run_score_analysis',
    'quick_engine_prep',
    'prepare_engine_metrics_for_ml',
    'feature_correlation_summary',
    'detect_outliers',
    'compute_pca_features',
]
