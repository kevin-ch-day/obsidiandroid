"""Per-model held-out predictions with full class probabilities."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder

from config import app_config
from obsidiandroid.diagnostics import headline_evaluation_export


def _fitted_result(model_seed: int) -> dict:
    """Tiny synthetic three-class fit; test rows are indexed by sample ID."""
    rng = np.random.default_rng(model_seed)
    raw_labels = np.array([101, 202, 303] * 10)
    encoder = LabelEncoder().fit(raw_labels)
    y = encoder.transform(raw_labels)
    X = pd.DataFrame(rng.normal(size=(30, 3)) + y[:, None], index=np.arange(1, 31))
    model = LogisticRegression(max_iter=500).fit(X.iloc[:24], y[:24])
    X_test, y_test = X.iloc[24:], y[24:]
    return {
        "model": model,
        "X_test": X_test,
        "y_test": y_test,
        "label_encoder": encoder,
        "evaluation": {"y_true": y_test, "y_pred": model.predict(X_test)},
    }


@pytest.fixture()
def _split_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        app_config, "RUNTIME_HEADLINE_SPLIT_METADATA", {"split_hash": "ab" * 32}, raising=False
    )
    monkeypatch.setattr(
        app_config,
        "RUNTIME_SPLIT_SAMPLE_METADATA",
        pd.DataFrame({"sample_id": np.arange(1, 31), "sha256": [f"{i:064x}" for i in range(1, 31)]}),
        raising=False,
    )


def test_every_model_writes_test_predictions_with_full_probabilities(
    tmp_path: Path, _split_runtime: None
) -> None:
    results = {"logistic_regression": _fitted_result(0), "random_forest": _fitted_result(1)}

    paths = headline_evaluation_export.export_model_test_predictions(
        results=results, diagnostics_dir=tmp_path, run_id="unit_run"
    )

    assert sorted(paths) == ["logistic_regression", "random_forest"]
    frame = pd.read_csv(paths["random_forest"])
    result = results["random_forest"]
    assert frame["sample_id"].tolist() == list(result["X_test"].index)
    assert frame["sha256"].tolist() == [f"{i:064x}" for i in result["X_test"].index]
    assert frame["split_role"].eq("test").all()
    assert frame["split_hash"].eq("ab" * 32).all()
    assert frame["true_label_id"].tolist() == [101, 202, 303, 101, 202, 303]
    proba_cols = ["proba__101", "proba__202", "proba__303"]
    assert [c for c in frame.columns if c.startswith("proba__")] == proba_cols
    np.testing.assert_allclose(frame[proba_cols].sum(axis=1), 1.0, atol=1e-6)
    expected = result["label_encoder"].inverse_transform(result["evaluation"]["y_pred"])
    assert frame["predicted_label_id"].tolist() == list(expected)


def test_models_without_probabilities_still_write_labels(
    tmp_path: Path, _split_runtime: None
) -> None:
    result = _fitted_result(2)

    class _NoProba:
        def predict(self, X):  # pragma: no cover - not called by the exporter
            raise AssertionError

    result["model"] = _NoProba()
    paths = headline_evaluation_export.export_model_test_predictions(
        results={"svm": result}, diagnostics_dir=tmp_path, run_id="unit_run"
    )
    frame = pd.read_csv(paths["svm"])
    assert len(frame) == 6
    assert not [c for c in frame.columns if c.startswith("proba__")]


def test_classifier_pipeline_writes_per_model_predictions_to_run_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from obsidiandroid.modeling import pipeline_core

    run_id = "20261019T000000Z__predexp"
    diagnostics_dir = tmp_path / "output" / "runs" / run_id / "diagnostics"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_FEATURE_CONTRACT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_LEAKAGE_ASSESSMENT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", 1, raising=False)
    monkeypatch.setattr(
        pipeline_core.distribution_reporter, "print_family_distribution", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        pipeline_core.distribution_reporter,
        "apply_min_family_support",
        lambda **kwargs: (kwargs["features_df"], kwargs["labels_df"], 0, 0, []),
    )
    fitted = _fitted_result(3)
    monkeypatch.setattr(
        pipeline_core, "train_models", lambda *_a, **_k: ({"logistic_regression": fitted}, [])
    )
    monkeypatch.setattr(pipeline_core, "summarize_models", lambda _results: "logistic_regression")
    monkeypatch.setattr(pipeline_core, "promote_default_model", lambda *_a, **_k: None)

    pipeline_core.run_classifier_pipeline(
        features_df=pd.DataFrame({"signal": [1.0, 2.0]}, index=["101", "102"]),
        samples_df=pd.DataFrame(
            {"sample_id": [101, 102], "family_id": [44, 51], "family_canonical": ["Irata", "SpyNote"]}
        ),
        save_model=False,
        models=["logistic_regression"],
    )

    assert (diagnostics_dir / f"test_predictions_logistic_regression_{run_id}.csv").is_file()
