import time
from pathlib import Path

import pandas as pd
import pytest
from sklearn.datasets import make_classification

from config import app_config
from obsidiandroid.modeling.ml_trainers import random_forest_trainer
from obsidiandroid.diagnostics import rf_feature_importance_export as rfexp
from obsidiandroid.evaluation import random_forest_diagnostics as rfd

pytestmark = pytest.mark.contract


def _make_dataset(n_samples):
    X, y = make_classification(
        n_samples=n_samples,
        n_features=20,
        n_informative=15,
        n_redundant=0,
        n_classes=3,
        random_state=0,
    )
    return pd.DataFrame(X), pd.Series(y)


def test_random_forest_training_time_small(monkeypatch):
    X, y = _make_dataset(400)
    monkeypatch.setattr(app_config, "RF_NUM_TREES", 10, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_RF_GRID_SEARCH", False, raising=False)
    start = time.perf_counter()
    _, result = random_forest_trainer.train_random_forest(
        X,
        y,
        verbose=False,
        grid_search=False,
    )
    duration = time.perf_counter() - start
    assert result["metadata"]["duration"] <= duration
    assert duration < 5


def test_random_forest_training_time_medium(monkeypatch):
    X, y = _make_dataset(1000)
    monkeypatch.setattr(app_config, "RF_NUM_TREES", 10, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_RF_GRID_SEARCH", False, raising=False)
    start = time.perf_counter()
    _, result = random_forest_trainer.train_random_forest(
        X,
        y,
        verbose=False,
        grid_search=False,
    )
    duration = time.perf_counter() - start
    assert result["metadata"]["duration"] <= duration
    assert duration < 15


def test_run_diagnostics_returns_metrics(monkeypatch):
    """Diagnostic helper should return a stable metric set."""
    monkeypatch.setattr(app_config, "RF_PARAM_GRID", {"n_estimators": [10], "max_depth": [2]}, raising=False)
    monkeypatch.setattr(app_config, "CV_FOLDS", 2, raising=False)
    res = rfd.run_diagnostics(
        n_samples=100,
        random_state=0,
        enable_grid_search=False,
        cross_validate=False,
    )
    assert 0.0 <= res["accuracy"] <= 1.0
    assert "cv_scores" in res
    assert isinstance(res["weak_classes"], list)
    assert isinstance(res["class_counts"], dict)
    assert "imbalance_ratio" in res


def test_oob_score_reporting(monkeypatch):
    """When OOB scoring is enabled, diagnostics should include numeric OOB score."""
    monkeypatch.setattr(app_config, "RF_ENABLE_OOB_SCORE", True, raising=False)
    res = rfd.run_diagnostics(
        n_samples=120,
        random_state=1,
        enable_grid_search=False,
        cross_validate=False,
    )
    assert "oob_score" in res
    assert res["oob_score"] is not None


def test_export_rf_impurity_importances_uses_global_latest_for_run_scoped_dirs(
    make_run_diagnostics_layout,
    monkeypatch,
) -> None:
    """Run-scoped RF importance CSV should write and mirror to diagnostics latest."""
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)

    class _DummyModel:
        feature_importances_ = [0.7, 0.3]

    out = rfexp.export_rf_impurity_importances_csv(
        model=_DummyModel(),
        feature_names=["perm__internet", "vendor_signal"],
        diagnostics_dir=diagnostics_dir,
        run_id="rid",
        top_k=2,
    )

    assert out == diagnostics_dir / "rf_impurity_importance_rid.csv"
    assert Path(out).is_file()
    assert not (diagnostics_dir / "rf_impurity_importance.latest.csv").exists()
    assert (output_root / "diagnostics" / "rf_impurity_importance.latest.csv").is_file()
