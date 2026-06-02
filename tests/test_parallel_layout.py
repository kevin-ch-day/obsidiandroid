"""Tests for adaptive parallelism caps in heavy runtime scopes."""

from config import app_config
from obsidiandroid.modeling import parallel_layout


def test_resolve_adaptive_job_count_caps_broad_corpus_training(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "ENABLE_ADAPTIVE_TRAINING_PARALLELISM", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_PROFILE_ID", "android_malware_all_current", raising=False)
    monkeypatch.setattr(app_config, "BROAD_CORPUS_TRAINING_N_JOBS_CAP", 2, raising=False)

    assert parallel_layout.resolve_adaptive_job_count(-1, kind="training") == 2


def test_resolve_adaptive_job_count_caps_ablation_more_strictly(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "ENABLE_ADAPTIVE_TRAINING_PARALLELISM", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_PROFILE_ID", "android_malware_all_current", raising=False)
    monkeypatch.setattr(app_config, "ABLATION_TRAINING_N_JOBS_CAP", 1, raising=False)

    assert parallel_layout.resolve_adaptive_job_count(-1, kind="training") == 1


def test_grid_search_job_counts_caps_outer_jobs_for_broad_corpus(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "ENABLE_ADAPTIVE_TRAINING_PARALLELISM", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_PROFILE_ID", "android_malware_all_current", raising=False)
    monkeypatch.setattr(app_config, "BROAD_CORPUS_CV_N_JOBS_CAP", 2, raising=False)
    monkeypatch.setattr(app_config, "CV_AVOID_NESTED_PARALLELISM", True, raising=False)
    monkeypatch.setattr(app_config, "CV_N_JOBS", -1, raising=False)

    inner, outer = parallel_layout.grid_search_job_counts()
    assert inner == 1
    assert outer == 2
