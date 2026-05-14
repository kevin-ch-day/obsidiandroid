# Filename: src/obsidiandroid/modeling/parallel_layout.py
# Purpose : Consistent CPU parallelism for ``GridSearchCV`` vs inner sklearn estimators.

"""Job-count helpers so grid search matches cross-validation parallelism policy."""

from __future__ import annotations

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
