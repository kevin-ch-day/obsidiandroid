"""Tests for runtime-default resolution in model trainer factory."""

from __future__ import annotations

import pandas as pd
from sklearn.datasets import make_classification

from config import app_config
from ml_classification.training import model_trainer_factory


def test_train_model_factory_resolves_runtime_split_defaults(monkeypatch) -> None:
    """Runtime config overrides should affect train/test split defaults at call time."""
    features, labels = make_classification(
        n_samples=80,
        n_features=6,
        n_informative=5,
        n_redundant=0,
        n_classes=3,
        random_state=11,
    )
    features_df = pd.DataFrame(features)
    labels_sr = pd.Series(labels)

    monkeypatch.setattr(app_config, "TRAIN_TEST_SPLIT", 0.40, raising=False)
    monkeypatch.setattr(app_config, "RANDOM_STATE", 123, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "runtime_defaults_test", raising=False)
    model_trainer_factory.reset_runtime_training_caches()

    result = model_trainer_factory.train_model_factory(
        features_df=features_df,
        labels=labels_sr,
        model_type="logistic_regression",
        cross_validate=False,
        enable_grid_search=False,
        use_smote=False,
    )

    assert isinstance(result, dict)
    assert len(result["X_test"]) == 32
