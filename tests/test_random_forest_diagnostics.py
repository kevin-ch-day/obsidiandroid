from obsidiandroid.evaluation import random_forest_diagnostics as rfd
from config import app_config


def test_run_diagnostics_returns_metrics(monkeypatch):
    monkeypatch.setattr(app_config, "RF_PARAM_GRID", {"n_estimators": [10], "max_depth": [2]}, raising=False)
    monkeypatch.setattr(app_config, "CV_FOLDS", 2, raising=False)
    res = rfd.run_diagnostics(
        n_samples=100,
        random_state=0,
        enable_grid_search=False,
        cross_validate=False,
    )
    assert 0.0 <= res['accuracy'] <= 1.0
    assert 'cv_scores' in res
    assert isinstance(res['weak_classes'], list)
    assert isinstance(res['class_counts'], dict)
    assert 'imbalance_ratio' in res


def test_oob_score_reporting(monkeypatch):
    monkeypatch.setattr(app_config, "RF_ENABLE_OOB_SCORE", True, raising=False)
    res = rfd.run_diagnostics(
        n_samples=120,
        random_state=1,
        enable_grid_search=False,
        cross_validate=False,
    )
    assert 'oob_score' in res
    assert res['oob_score'] is not None
