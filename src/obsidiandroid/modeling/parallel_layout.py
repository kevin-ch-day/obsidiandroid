# Filename: src/obsidiandroid/modeling/parallel_layout.py
# Purpose : Consistent CPU parallelism for ``GridSearchCV`` vs inner sklearn estimators.

"""Job-count and CV-splitter helpers for modeling grid search.

``GridSearchCV`` uses :func:`grid_search_job_counts` for CPU parallelism policy
(aligned with :func:`obsidiandroid.modeling.training_helpers.perform_cross_validation`)
and :func:`stratified_kfold_for_grid_search` for a valid ``StratifiedKFold`` splitter
(at least two folds; rare-class safe).
"""

from __future__ import annotations

import os

from sklearn.model_selection import StratifiedKFold

from config import app_config

from obsidiandroid.common.cv_fold_config import (
    coerce_stratified_cv_folds_config,
    safe_int_config_value,
)


def _profile_parallelism_scope() -> str:
    """Return the active runtime scope for adaptive parallelism decisions."""
    if bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)):
        return "ablation"
    profile_id = str(getattr(app_config, "RUNTIME_PROFILE_ID", "") or "").strip().lower()
    if profile_id == "android_malware_all_current":
        return "broad_corpus"
    return "default"


def _resolve_parallel_cap(scope: str, *, kind: str) -> int | None:
    """Return an adaptive job cap for the current runtime scope, if any."""
    if not bool(getattr(app_config, "ENABLE_ADAPTIVE_TRAINING_PARALLELISM", True)):
        return None
    key_map = {
        ("broad_corpus", "training"): "BROAD_CORPUS_TRAINING_N_JOBS_CAP",
        ("ablation", "training"): "ABLATION_TRAINING_N_JOBS_CAP",
        ("broad_corpus", "cv"): "BROAD_CORPUS_CV_N_JOBS_CAP",
        ("ablation", "cv"): "ABLATION_CV_N_JOBS_CAP",
    }
    key = key_map.get((scope, kind))
    if not key:
        return None
    value = safe_int_config_value(getattr(app_config, key, 0), default=0)
    if value <= 0:
        return None
    return value


def resolve_adaptive_job_count(
    requested_n_jobs: int,
    *,
    kind: str,
) -> int:
    """Return ``requested_n_jobs`` adjusted for broad-corpus/ablation runtime caps."""
    scope = _profile_parallelism_scope()
    cap = _resolve_parallel_cap(scope, kind=kind)
    if cap is None:
        return requested_n_jobs

    cpu_count = max(1, int(os.cpu_count() or 1))
    effective_requested = cpu_count if int(requested_n_jobs) == -1 else max(1, int(requested_n_jobs))
    return max(1, min(effective_requested, int(cap)))


def grid_search_job_counts() -> tuple[int, int]:
    """Return ``(inner_estimator_n_jobs, gridsearchcv_n_jobs)``.

    When :data:`config.settings.tuning_cv.CV_AVOID_NESTED_PARALLELISM` is true (default),
    inner tree/linear/boost estimators run single-threaded while ``GridSearchCV`` uses
    :data:`config.settings.tuning_cv.CV_N_JOBS` for parallel parameter evaluations—the same
    idea as :func:`obsidiandroid.modeling.training_helpers.perform_cross_validation`.

    When the guard is false, both values default to ``-1`` (legacy aggressive nesting).
    """
    outer = safe_int_config_value(getattr(app_config, "CV_N_JOBS", -1), default=-1)
    outer = resolve_adaptive_job_count(outer, kind="cv")
    if bool(getattr(app_config, "CV_AVOID_NESTED_PARALLELISM", True)):
        return 1, outer
    return resolve_adaptive_job_count(-1, kind="training"), outer


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
    configured = coerce_stratified_cv_folds_config(getattr(app_config, "CV_FOLDS", 5))
    n_splits = min(configured, min_class_support)
    return StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
