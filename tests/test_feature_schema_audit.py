"""Tests for ablation feature schema audit rows."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from config import app_config
from ml_classification.training import feature_schema_audit


def test_schema_audit_ok_when_names_match(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_EXPERIMENT_ID", "vendor_only", raising=False)
    X = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    m = LogisticRegression()
    m.fit(X, [0, 1])
    row = feature_schema_audit.build_ablation_schema_audit_row(
        model=m, model_type="logistic_regression", features_df=X
    )
    assert row["status"] == "OK"
    assert row["missing_at_predict_count"] == 0
    assert row["extra_at_predict_count"] == 0


def test_schema_audit_detects_extra_columns(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_EXPERIMENT_ID", "permissions_only", raising=False)
    fit_df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    m = LogisticRegression()
    m.fit(fit_df, [0, 1])
    pred_df = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [0, 0]})
    row = feature_schema_audit.build_ablation_schema_audit_row(
        model=m, model_type="logistic_regression", features_df=pred_df
    )
    assert row["status"] == "schema_mismatch"
    assert row["extra_at_predict_count"] == 1
