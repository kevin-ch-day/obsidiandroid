"""Ensure ablation reuses train/test indices but not cached feature matrices."""

import numpy as np
import pandas as pd

from config import app_config
from obsidiandroid.modeling import model_trainer_factory


def test_ablation_split_cache_reslices_current_feature_columns(monkeypatch) -> None:
    """Second feature matrix must train with its own columns when split cache hits."""
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "ut_ablation_cols", raising=False)
    monkeypatch.setattr(app_config, "TRAIN_TEST_SPLIT", 0.33)
    monkeypatch.setattr(app_config, "RANDOM_STATE", 0)
    monkeypatch.setattr(app_config, "ENABLE_SMOTE_OVERSAMPLING", False)
    monkeypatch.setattr(model_trainer_factory, "_export_split_audit", lambda **_kw: None)
    model_trainer_factory.reset_runtime_training_caches()

    captured: list[list[str]] = []

    def _fake_trainer(**kwargs):
        captured.append(list(kwargs["X_train"].columns))
        fit_cols = list(kwargs["X_train"].columns)

        class _Dummy:
            feature_names_in_ = np.array(fit_cols)

            def predict(self, X):
                return np.zeros(len(X))

            def predict_proba(self, X):
                return np.ones((len(X), 2)) * 0.5

        return _Dummy(), {}

    monkeypatch.setattr(model_trainer_factory, "get_model_trainer", lambda _mt: _fake_trainer)

    idx = list(range(30))
    labels = pd.Series((["a", "b", "c"] * 10)[:30], index=idx)
    df_vendor = pd.DataFrame({f"v{i}": np.arange(30) + i for i in range(2)}, index=idx)
    df_perm = pd.DataFrame({f"p{i}": np.arange(30) * i for i in range(3)}, index=idx)

    model_trainer_factory.train_model_factory(
        features_df=df_vendor,
        labels=labels,
        model_type="logistic_regression",
    )
    model_trainer_factory.train_model_factory(
        features_df=df_perm,
        labels=labels,
        model_type="logistic_regression",
    )

    assert len(captured) == 2
    assert all(c.startswith("v") for c in captured[0])
    assert all(c.startswith("p") for c in captured[1])
