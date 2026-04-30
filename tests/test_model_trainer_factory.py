import os
import sys
import pandas as pd
import numpy as np
import pytest
from sklearn.datasets import make_classification

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ml_classification.training import model_trainer_factory
from config import app_config


def _imbalanced_data():
    X, y = make_classification(
        n_samples=200,
        n_features=6,
        n_informative=5,
        n_redundant=0,
        n_classes=2,
        weights=[0.9, 0.1],
        random_state=0,
    )
    return pd.DataFrame(X), pd.Series(y)


def test_smote_oversampling_increases_training_size():
    """sample_ids_train tracks pre-SMOTE split IDs by contract."""
    X, y = _imbalanced_data()
    result = model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="random_forest",
        use_smote=True,
        enable_grid_search=False,
        random_state=0,
    )
    expected_min = int(len(y) * (1 - app_config.TRAIN_TEST_SPLIT))
    assert len(result["sample_ids_train"]) == expected_min


def test_balanced_split_adjusts_size(monkeypatch):
    X, y = _imbalanced_data()
    monkeypatch.setattr(app_config, "AUTO_ADJUST_TRAIN_TEST_SPLIT", True, raising=False)
    monkeypatch.setattr(app_config, "MIN_TEST_SAMPLES_PER_CLASS", 2, raising=False)
    result = model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="random_forest",
        enable_grid_search=False,
        random_state=0,
        test_size=0.2,
    )
    from collections import Counter
    counts = Counter(result["y_test"])
    assert min(counts.values()) >= 2


def test_factory_nan_input():
    X, y = _imbalanced_data()
    X.iloc[0, 0] = np.nan
    with pytest.raises(ValueError):
        model_trainer_factory.train_model_factory(X, y)


def test_factory_inf_input():
    X, y = _imbalanced_data()
    X.iloc[0, 1] = np.inf
    with pytest.raises(ValueError):
        model_trainer_factory.train_model_factory(X, y)


def test_factory_balanced_random_forest_runs():
    X, y = _imbalanced_data()
    result = model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="balanced_random_forest",
        enable_grid_search=False,
        random_state=0,
    )
    assert "predictions" in result
    assert len(result["predictions"]) == len(result["y_test"])


def test_smote_not_called_for_balanced_random_forest(monkeypatch):
    X, y = _imbalanced_data()

    call_tracker = {"called": False}

    def fake_apply_smote(X_train, y_train, random_state):
        call_tracker["called"] = True
        return X_train, y_train

    monkeypatch.setattr(model_trainer_factory, "apply_smote", fake_apply_smote)

    model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="balanced_random_forest",
        use_smote=True,
        enable_grid_search=False,
        random_state=0,
    )

    assert not call_tracker["called"]


def test_smote_respects_runtime_flag_when_use_smote_not_explicit(monkeypatch):
    X, y = _imbalanced_data()
    call_tracker = {"called": False}

    def fake_apply_smote(X_train, y_train, random_state):
        call_tracker["called"] = True
        return X_train, y_train

    monkeypatch.setattr(app_config, "ENABLE_SMOTE_OVERSAMPLING", False, raising=False)
    monkeypatch.setattr(model_trainer_factory, "apply_smote", fake_apply_smote)

    model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="random_forest",
        enable_grid_search=False,
        random_state=0,
    )

    assert not call_tracker["called"]


def test_train_test_split_is_reused_across_models(monkeypatch):
    X, y = _imbalanced_data()
    split_calls = {"count": 0}
    original_split = model_trainer_factory.train_test_split

    def counting_split(*args, **kwargs):
        split_calls["count"] += 1
        return original_split(*args, **kwargs)

    def fake_trainer(**kwargs):
        y_test = kwargs["y_test"]
        label_encoder = kwargs["label_encoder"]
        return object(), {
            "predictions": [int(y_test[0])] * len(y_test),
            "true_labels": list(y_test),
            "confidences": np.ones(len(y_test)),
            "label_encoder": label_encoder,
            "label_classes": list(label_encoder.classes_),
        }

    monkeypatch.setattr(app_config, "AUTO_ADJUST_TRAIN_TEST_SPLIT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "cache_reuse_test", raising=False)
    monkeypatch.setattr(model_trainer_factory, "train_test_split", counting_split)
    monkeypatch.setattr(model_trainer_factory, "get_model_trainer", lambda _: fake_trainer)
    model_trainer_factory.reset_runtime_training_caches()

    model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="random_forest",
        use_smote=False,
        enable_grid_search=False,
        random_state=0,
    )
    model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="xgboost",
        use_smote=False,
        enable_grid_search=False,
        random_state=0,
    )

    assert split_calls["count"] == 1
