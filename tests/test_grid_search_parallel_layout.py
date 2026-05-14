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
