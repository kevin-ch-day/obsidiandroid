"""Tests for ``obsidiandroid.modeling.parallel_layout``."""

from __future__ import annotations


def test_grid_search_job_counts_defaults_to_nested_guard(monkeypatch) -> None:
    from config import app_config
    from obsidiandroid.modeling.parallel_layout import grid_search_job_counts

    monkeypatch.setattr(app_config, "CV_AVOID_NESTED_PARALLELISM", True, raising=False)
    monkeypatch.setattr(app_config, "CV_N_JOBS", -1, raising=False)
    inner, outer = grid_search_job_counts()
    assert inner == 1
    assert outer == -1


def test_grid_search_job_counts_legacy_parallelism(monkeypatch) -> None:
    from config import app_config
    from obsidiandroid.modeling.parallel_layout import grid_search_job_counts

    monkeypatch.setattr(app_config, "CV_AVOID_NESTED_PARALLELISM", False, raising=False)
    monkeypatch.setattr(app_config, "CV_N_JOBS", 4, raising=False)
    inner, outer = grid_search_job_counts()
    assert inner == -1
    assert outer == -1


def test_grid_search_job_counts_respects_cv_n_jobs(monkeypatch) -> None:
    from config import app_config
    from obsidiandroid.modeling.parallel_layout import grid_search_job_counts

    monkeypatch.setattr(app_config, "CV_AVOID_NESTED_PARALLELISM", True, raising=False)
    monkeypatch.setattr(app_config, "CV_N_JOBS", 2, raising=False)
    inner, outer = grid_search_job_counts()
    assert inner == 1
    assert outer == 2


def test_stratified_kfold_for_grid_search_none_when_rare_class_tiny() -> None:
    from obsidiandroid.modeling.parallel_layout import stratified_kfold_for_grid_search

    assert stratified_kfold_for_grid_search(1, random_state=0) is None


def test_stratified_kfold_for_grid_search_respects_cv_folds_and_support(monkeypatch) -> None:
    from config import app_config
    from obsidiandroid.modeling.parallel_layout import stratified_kfold_for_grid_search

    monkeypatch.setattr(app_config, "CV_FOLDS", 5, raising=False)
    cv = stratified_kfold_for_grid_search(10, random_state=42)
    assert cv is not None
    assert cv.n_splits == 5

    cv2 = stratified_kfold_for_grid_search(2, random_state=0)
    assert cv2 is not None
    assert cv2.n_splits == 2


def test_stratified_kfold_for_grid_search_caps_at_class_support(monkeypatch) -> None:
    from config import app_config
    from obsidiandroid.modeling.parallel_layout import stratified_kfold_for_grid_search

    monkeypatch.setattr(app_config, "CV_FOLDS", 7, raising=False)
    cv = stratified_kfold_for_grid_search(3, random_state=1)
    assert cv is not None
    assert cv.n_splits == 3
