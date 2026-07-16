"""Regression coverage for the lightweight model-training facade."""

import pandas as pd

from config import app_config
from obsidiandroid.modeling import model_training


def test_xgboost_grid_flag_is_forwarded_to_factory(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_factory(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(app_config, "ENABLE_XGB_GRID_SEARCH", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_QUIET_TRAINING", True, raising=False)
    monkeypatch.setattr(model_training.model_trainer_factory, "train_model_factory", _fake_factory)

    result = model_training.train_model(
        "xgboost",
        pd.DataFrame({"feature": [0, 1, 2]}),
        pd.Series([0, 1, 1]),
    )

    assert result == {"ok": True}
    assert captured["model_type"] == "xgboost"
    assert captured["enable_grid_search"] is True
