# Filename: src/obsidiandroid/modeling/parallel_layout.py
# Purpose : Consistent CPU parallelism for ``GridSearchCV`` vs inner sklearn estimators.

"""Job-count and CV-splitter helpers for modeling grid search.

``GridSearchCV`` uses :func:`grid_search_job_counts` for CPU parallelism policy
(aligned with :func:`obsidiandroid.modeling.training_helpers.perform_cross_validation`)
and :func:`stratified_kfold_for_grid_search` for a valid ``StratifiedKFold`` splitter
(at least two folds; rare-class safe).
"""

from __future__ import annotations

from sklearn.model_selection import StratifiedKFold

from config import app_config


def grid_search_job_counts() -> tuple[int, int]:
    """Return ``(inner_estimator_n_jobs, gridsearchcv_n_jobs)``.

    When :data:`config.settings.tuning_cv.CV_AVOID_NESTED_PARALLELISM` is true (default),
    inner tree/linear/boost estimators run single-threaded while ``GridSearchCV`` uses
    :data:`config.settings.tuning_cv.CV_N_JOBS` for parallel parameter evaluations—the same
    idea as :func:`obsidiandroid.modeling.training_helpers.perform_cross_validation`.

    When the guard is false, both values default to ``-1`` (legacy aggressive nesting).
    """
    outer = int(getattr(app_config, "CV_N_JOBS", -1))
    if bool(getattr(app_config, "CV_AVOID_NESTED_PARALLELISM", True)):
        return 1, outer
    return -1, -1


def stratified_kfold_for_grid_search(
    min_class_support: int,
    *,
    random_state: int,
) -> StratifiedKFold | None:
    """Stratified K-fold splitter for ``GridSearchCV``, or ``None`` if unusable.

    ``GridSearchCV`` requires at least two splits; stratified folds further require
    at least **two** samples in the rarest class. When that is not met, callers
    should skip grid search and fit a single estimator with default parameters.
    """
    if min_class_support < 2:
        return None
    configured = max(2, int(getattr(app_config, "CV_FOLDS", 5)))
    n_splits = min(configured, min_class_support)
    return StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
