import numpy as np
import pandas as pd
import os
import json
import warnings

from config import app_config
from obsidiandroid.modeling import model_prediction
from obsidiandroid.modeling import pipeline_core
from obsidiandroid.modeling import feature_selection_contract as selection


class _DummyEncoder:
    classes_ = np.array(["Anubis", "other"])


def test_align_data_returns_series() -> None:
    features = pd.DataFrame({"feat": [1, 2]}, index=["s1", "s2"])
    labels = pd.DataFrame({"sample_id": ["s1", "s2"], "family_name": ["A", "B"]})
    f, lbl = pipeline_core.align_data(features, labels)
    assert isinstance(lbl, pd.Series)
    assert list(f.index) == ["s1", "s2"]


def test_configured_models_defaults_to_fast_mode(monkeypatch):
    monkeypatch.setattr(app_config, "ENABLE_BENCHMARK_MODELS", False, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_TRAINING_MODELS", ["xgboost"], raising=False)
    models = pipeline_core._get_configured_models(None)
    assert models == ["xgboost"]


def test_configured_models_uses_benchmark_set(monkeypatch):
    monkeypatch.setattr(app_config, "ENABLE_BENCHMARK_MODELS", True, raising=False)
    monkeypatch.setattr(
        app_config,
        "BENCHMARK_TRAINING_MODELS",
        ["xgboost", "random_forest"],
        raising=False,
    )
    models = pipeline_core._get_configured_models(None)
    assert models == ["xgboost", "random_forest"]


def test_training_checkpoint_halts_remaining_headline_models_after_failure(monkeypatch, tmp_path) -> None:
    """An invalid first model must not spend time training the remaining models."""
    attempted: list[str] = []
    observed_checkpoint: dict[str, object] = {}
    monkeypatch.setattr(app_config, "FAIL_FAST_TRAINING_MODEL_FAILURES", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "checkpoint_run", raising=False)
    monkeypatch.setattr(pipeline_core, "_diagnostics_dir", lambda: tmp_path)
    def invalid_result(model_type, **_kwargs):
        attempted.append(model_type)
        observed_checkpoint.update(
            json.loads((tmp_path / "training_checkpoint_checkpoint_run.json").read_text(encoding="utf-8"))
        )
        return {}

    monkeypatch.setattr(pipeline_core.train_model_executor, "train_and_evaluate_model", invalid_result)
    monkeypatch.setattr(pipeline_core.ml_result_validator, "validate_result_structure", lambda _result: False)

    results, skipped = pipeline_core.train_models(
        pd.DataFrame({"feature": [0, 1]}),
        pd.Series([0, 1]),
        models=["random_forest", "xgboost"],
        save_model=False,
    )

    checkpoint = json.loads((tmp_path / "training_checkpoint_checkpoint_run.json").read_text(encoding="utf-8"))
    assert results == {}
    assert skipped == ["random_forest"]
    assert attempted == ["random_forest"]
    assert observed_checkpoint["state"] == "model_started"
    assert observed_checkpoint["current_model"] == "random_forest"
    assert checkpoint["state"] == "halted"
    assert checkpoint["next_model"] == "xgboost"


def test_primary_feature_contract_blocks_target_adjacent_av_semantics(monkeypatch):
    monkeypatch.setattr(app_config, "ENABLE_LABEL_DERIVED_VENDOR_FEATURES", False, raising=False)
    frame = pd.DataFrame(
        {
            "perm__internet": [1, 0],
            "parsed_family_vendor": [3, 4],
            "vendor_parsed_threat_class_vendor": [1, 2],
            "meta__has_vt_suggested_threat_label": [1, 0],
        }
    )
    contract = selection.fit_feature_selection_contract(frame, pd.Series([10, 11]))
    out = selection.apply_feature_selection_contract(frame, contract)
    assert list(out.columns) == ["perm__internet"]
    reasons = {row["column_name"]: row["reason_code"] for row in contract["leakage_pruning_audit"]}
    assert reasons["parsed_family_vendor"] == "label_independent_contract_block"
    assert reasons["vendor_parsed_threat_class_vendor"] == "label_independent_contract_block"
    assert reasons["meta__has_vt_suggested_threat_label"] == "label_independent_contract_block"


def test_low_confidence_abstain_routes_to_other(monkeypatch):
    monkeypatch.setattr(app_config, "ENABLE_LOW_CONFIDENCE_ABSTAIN", True, raising=False)
    monkeypatch.setattr(app_config, "LOW_CONFIDENCE_THRESHOLD", 0.30, raising=False)
    monkeypatch.setattr(app_config, "LOW_CONFIDENCE_MARGIN_THRESHOLD", 0.0, raising=False)
    monkeypatch.setattr(app_config, "ABSTAIN_LABEL", "other", raising=False)

    y_pred = np.array([0, 0, 0])  # all Anubis initially
    y_conf = np.array([0.95, 0.29, 0.05])
    out, meta = model_prediction._apply_low_confidence_abstain(y_pred, y_conf, _DummyEncoder())
    assert out.tolist() == [0, 1, 1]
    assert meta[1]["abstain_reasons"] == ["low_confidence"]


class _TriEncoder:
    classes_ = np.array(["Anubis", "BankBot", "other"])


def test_benchmark_family_guardrail_abstains_on_ambiguous_margin(monkeypatch):
    monkeypatch.setattr(app_config, "ENABLE_LOW_CONFIDENCE_ABSTAIN", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_BENCHMARK_ABSTAIN_GUARDRAIL", True, raising=False)
    monkeypatch.setattr(app_config, "BENCHMARK_LOW_CONFIDENCE_THRESHOLD", 0.45, raising=False)
    monkeypatch.setattr(app_config, "BENCHMARK_LOW_CONFIDENCE_MARGIN_THRESHOLD", 0.15, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SUPPORT_FLOOR_MODE", "benchmark_eligibility", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD", "family_id", raising=False)
    monkeypatch.setattr(app_config, "ABSTAIN_LABEL", "other", raising=False)

    y_pred = np.array([0, 1])
    y_conf = np.array([0.51, 0.83])
    y_prob = np.array(
        [
            [0.51, 0.44, 0.05],
            [0.83, 0.10, 0.07],
        ]
    )
    out, meta = model_prediction._apply_low_confidence_abstain(
        y_pred, y_conf, _TriEncoder(), y_prob=y_prob
    )
    assert out.tolist() == [2, 1]
    assert meta[0]["abstain_reasons"] == ["low_margin"]
    assert meta[0]["raw_prediction_label"] == "Anubis"


def test_suppress_known_sklearn_parallel_warning_is_narrow() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pipeline_core._suppress_known_sklearn_parallel_warning():
            warnings.warn(
                "`sklearn.utils.parallel.delayed` should be used with "
                "`sklearn.utils.parallel.Parallel` to make it possible to "
                "propagate the scikit-learn configuration of the current thread to "
                "the joblib workers.",
                UserWarning,
            )
            warnings.warn("some other warning", UserWarning)

    messages = [str(w.message) for w in caught]
    assert messages == ["some other warning"]


def test_suppress_known_sklearn_parallel_warning_restores_pythonwarnings_env(monkeypatch) -> None:
    monkeypatch.setenv("PYTHONWARNINGS", "default")
    with pipeline_core._suppress_known_sklearn_parallel_warning():
        merged = os.environ["PYTHONWARNINGS"]
        assert "default" in merged
        assert "ignore::UserWarning:sklearn.utils.parallel" in merged
    assert os.environ["PYTHONWARNINGS"] == "default"
