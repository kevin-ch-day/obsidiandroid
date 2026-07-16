"""Tests for train-only feature selection and frozen column contracts."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from config import app_config
from obsidiandroid.modeling import feature_selection_contract as selection
from obsidiandroid.modeling import model_trainer_factory


def test_selection_is_fit_only_on_training_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config, "ENABLE_LABEL_DERIVED_VENDOR_FEATURES", False, raising=False)
    X_train = pd.DataFrame(
        {
            "train_constant": [0, 0, 0, 0],
            "varies": [0, 1, 0, 1],
            "parsed_family_vendor": [1, 2, 1, 2],
        },
        index=[10, 11, 12, 13],
    )
    X_test = pd.DataFrame(
        {
            "train_constant": [7, 8],
            "varies": [1, 0],
            "parsed_family_vendor": [9, 9],
        },
        index=[14, 15],
    )

    contract = selection.fit_feature_selection_contract(X_train, pd.Series([0, 1, 0, 1]))
    selected_test = selection.apply_feature_selection_contract(X_test, contract)

    assert contract["selection_scope"] == "train_partition_only"
    assert contract["retained_feature_columns"] == ["varies"]
    assert list(selected_test.columns) == ["varies"]
    assert "train_constant" in contract["dropped_low_information_columns"]
    assert "parsed_family_vendor" in contract["dropped_leakage_columns"]


def test_scoped_ablation_can_retain_label_adjacent_columns_without_relaxing_headline_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Leakage-sensitive ablations must run, while the global headline flag remains off."""
    monkeypatch.setattr(app_config, "ENABLE_LABEL_DERIVED_VENDOR_FEATURES", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ALLOW_LABEL_ADJACENT_FEATURES", True, raising=False)

    features = pd.DataFrame(
        {"parsed_family_vendor": [0, 1, 0, 1], "threat_class_vendor": [1, 1, 2, 2]},
        index=[10, 11, 12, 13],
    )
    contract = selection.fit_feature_selection_contract(features, pd.Series([0, 1, 0, 1]))

    assert contract["retained_feature_columns"] == ["parsed_family_vendor", "threat_class_vendor"]
    assert contract["dropped_leakage_columns"] == []
    assert contract["ablation_label_adjacent_features_allowed"] is True


def test_column_name_normalization_rejects_collisions() -> None:
    with pytest.raises(ValueError, match="collide after string normalization"):
        selection.normalize_feature_column_names(pd.DataFrame([[1, 2]], columns=[1, "1"]))


def test_selection_detects_identifier_column_matching_sample_index() -> None:
    features = pd.DataFrame(
        {"opaque_identifier": ["10", "11"], "signal": [0, 1]},
        index=[10, 11],
    )
    contract = selection.fit_feature_selection_contract(features, pd.Series([0, 1]))
    assert "opaque_identifier" in contract["dropped_leakage_columns"]
    assert any(
        row["reason_code"] == "matches_sample_id_index"
        for row in contract["leakage_pruning_audit"]
    )


def test_factory_applies_train_fitted_contract_to_test_partition(monkeypatch: pytest.MonkeyPatch) -> None:
    features = pd.DataFrame(
        {
            "signal": [0, 1, 0, 1, 0, 1],
            "heldout_only_variation": [0, 0, 0, 0, 3, 4],
        },
        index=[10, 11, 12, 13, 14, 15],
    )
    labels = pd.Series([0, 1, 0, 1, 0, 1], index=features.index)
    captured: dict[str, pd.DataFrame] = {}

    def fake_split(X, y, **_kwargs):
        return X.iloc[:4], X.iloc[4:], np.asarray(y)[:4], np.asarray(y)[4:]

    def fake_trainer(**kwargs):
        captured["train"] = kwargs["X_train"]
        captured["test"] = kwargs["X_test"]
        return object(), {"predictions": {}, "true_labels": {}, "confidence_scores": {}}

    monkeypatch.setattr(model_trainer_factory, "train_test_split", fake_split)
    monkeypatch.setattr(model_trainer_factory, "get_model_trainer", lambda _model: fake_trainer)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_FEATURE_CONTRACT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_LEAKAGE_ASSESSMENT_EXPORT", False, raising=False)
    model_trainer_factory.reset_runtime_training_caches()

    result = model_trainer_factory.train_model_factory(
        features,
        labels,
        model_type="random_forest",
        use_smote=False,
        random_state=42,
    )

    assert list(captured["train"].columns) == ["signal"]
    assert list(captured["test"].columns) == ["signal"]
    assert result["feature_selection_contract"]["retained_feature_columns"] == ["signal"]
