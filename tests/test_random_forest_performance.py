import os
import sys
import time
import pandas as pd
from sklearn.datasets import make_classification

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ml_classification.training.ml_trainers import random_forest_trainer
from config import app_config


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
