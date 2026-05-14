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


def test_grid_search_job_counts_cv_n_jobs_none_falls_back(monkeypatch) -> None:
    from config import app_config
    from obsidiandroid.modeling.parallel_layout import grid_search_job_counts

    monkeypatch.setattr(app_config, "CV_AVOID_NESTED_PARALLELISM", True, raising=False)
    monkeypatch.setattr(app_config, "CV_N_JOBS", None, raising=False)
    inner, outer = grid_search_job_counts()
    assert inner == 1
    assert outer == -1


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


def test_stratified_kfold_coerces_cv_folds_below_two(monkeypatch) -> None:
    from config import app_config
    from obsidiandroid.modeling.parallel_layout import stratified_kfold_for_grid_search

    monkeypatch.setattr(app_config, "CV_FOLDS", 1, raising=False)
    cv = stratified_kfold_for_grid_search(6, random_state=0)
    assert cv is not None
    assert cv.n_splits == 2

    monkeypatch.setattr(app_config, "CV_FOLDS", 7, raising=False)
    cv = stratified_kfold_for_grid_search(3, random_state=1)
    assert cv is not None
    assert cv.n_splits == 3


def test_coerce_stratified_cv_folds_config() -> None:
    from obsidiandroid.common.cv_fold_config import (
        coerce_stratified_cv_folds_config,
        safe_int_config_value,
    )

    assert coerce_stratified_cv_folds_config(None) == 5
    assert coerce_stratified_cv_folds_config("not_a_number") == 5
    assert coerce_stratified_cv_folds_config(1) == 2
    assert coerce_stratified_cv_folds_config(0) == 2
    assert coerce_stratified_cv_folds_config("4") == 4
    assert coerce_stratified_cv_folds_config(8, default=3) == 8

    assert safe_int_config_value(None, default=7) == 7
    assert safe_int_config_value("x", default=2) == 2
    assert safe_int_config_value("9", default=0) == 9


def test_stratified_kfold_treats_cv_folds_none_as_default(monkeypatch) -> None:
    from config import app_config
    from obsidiandroid.modeling.parallel_layout import stratified_kfold_for_grid_search

    monkeypatch.setattr(app_config, "CV_FOLDS", None, raising=False)
    cv = stratified_kfold_for_grid_search(10, random_state=0)
    assert cv is not None
    assert cv.n_splits == 5


def test_safe_float_config_value() -> None:
    from obsidiandroid.common.cv_fold_config import safe_float_config_value

    assert safe_float_config_value(None, default=0.25) == 0.25
    assert safe_float_config_value("bad", default=1.5) == 1.5
    assert safe_float_config_value("0.1", default=0.0) == 0.1


def test_resolve_training_runtime_defaults_tolerates_none_config(monkeypatch) -> None:
    from config import app_config
    from obsidiandroid.modeling import model_trainer_factory

    monkeypatch.setattr(app_config, "TRAIN_TEST_SPLIT", None, raising=False)
    monkeypatch.setattr(app_config, "RANDOM_STATE", None, raising=False)
    ts, rs = model_trainer_factory._resolve_training_runtime_defaults(None, None)
    assert ts == 0.25
    assert rs == 42
