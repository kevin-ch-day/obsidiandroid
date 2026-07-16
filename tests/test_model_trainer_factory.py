from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.datasets import make_classification

from obsidiandroid.modeling import model_trainer_factory
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


def test_factory_rejects_duplicate_sample_indices() -> None:
    X, y = _imbalanced_data()
    X.index = [0, 0] + list(range(2, len(X)))
    with pytest.raises(ValueError, match="duplicate sample IDs"):
        model_trainer_factory.train_model_factory(X, y)


def test_split_cache_key_changes_when_label_order_changes(monkeypatch) -> None:
    """A cache hit must represent the exact ordered sample/label pairing."""
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    features = pd.DataFrame({"f": [1.0, 2.0, 3.0, 4.0]}, index=[10, 20, 30, 40])
    first = model_trainer_factory._build_split_cache_key(
        features, np.array([0, 1, 0, 1]), 0.25, 42, group_aware_requested=False
    )
    changed_labels = model_trainer_factory._build_split_cache_key(
        features, np.array([1, 0, 0, 1]), 0.25, 42, group_aware_requested=False
    )
    reordered_ids = model_trainer_factory._build_split_cache_key(
        features.reindex([20, 10, 30, 40]), np.array([0, 1, 0, 1]), 0.25, 42,
        group_aware_requested=False,
    )
    assert first != changed_labels
    assert first != reordered_ids


def test_lineage_groups_keep_package_sha_then_sample_id_precedence(monkeypatch) -> None:
    monkeypatch.setattr(
        app_config,
        "RUNTIME_SPLIT_SAMPLE_METADATA",
        pd.DataFrame(
            {
                "sample_id": [10, 20, 30, 40],
                "package_name": ["com.example", "com.example", "", ""],
                "sha256": ["a", "b", "same", ""],
            }
        ),
        raising=False,
    )
    groups, note = model_trainer_factory._build_lineage_groups_for_split(  # pylint: disable=protected-access
        pd.DataFrame({"f": [1, 2, 3, 4]}, index=[10, 20, 30, 40])
    )
    assert note == "ok"
    assert groups is not None
    assert groups[0] == groups[1]
    assert groups[2] != groups[0]
    assert groups[3] != groups[2]


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


def test_smote_skipped_in_evidence_when_disable_flag(monkeypatch):
    X, y = _imbalanced_data()
    call_tracker = {"called": False}

    def fake_apply_smote(X_train, y_train, random_state):
        call_tracker["called"] = True
        return X_train, y_train

    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_MODE", True, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_SMOTE_OVERSAMPLING", True, raising=False)
    monkeypatch.setattr(app_config, "DISABLE_SMOTE_IN_EVIDENCE_MODE", True, raising=False)
    monkeypatch.setattr(model_trainer_factory, "apply_smote", fake_apply_smote)

    model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="random_forest",
        use_smote=True,
        enable_grid_search=False,
        random_state=0,
    )

    assert not call_tracker["called"]


def test_smote_warns_in_evidence_when_not_disabled(monkeypatch):
    X, y = _imbalanced_data()
    warnings: list[str] = []

    def capture_warning(msg: str, *args, **kwargs) -> None:
        warnings.append(str(msg))

    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_MODE", True, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_SMOTE_OVERSAMPLING", True, raising=False)
    monkeypatch.setattr(app_config, "DISABLE_SMOTE_IN_EVIDENCE_MODE", False, raising=False)
    monkeypatch.setattr(model_trainer_factory.du, "print_warning", capture_warning)

    model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="random_forest",
        use_smote=True,
        enable_grid_search=False,
        random_state=0,
    )

    assert any("[SMOTE]" in w for w in warnings)
    assert "[SMOTE] Synthetic oversampling remains enabled in evidence/paper mode by explicit configuration;" in str(
        getattr(app_config, "RUNTIME_SMOTE_WARNING_LAST", "")
    )


def test_smote_warning_is_emitted_once_per_run(monkeypatch):
    X, y = _imbalanced_data()
    warnings: list[str] = []

    def capture_warning(msg: str, *args, **kwargs) -> None:
        warnings.append(str(msg))

    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_MODE", True, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_SMOTE_OVERSAMPLING", True, raising=False)
    monkeypatch.setattr(app_config, "DISABLE_SMOTE_IN_EVIDENCE_MODE", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SMOTE_WARNING_LAST", "", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SMOTE_WARNING_EMITTED", False, raising=False)
    monkeypatch.setattr(model_trainer_factory.du, "print_warning", capture_warning)

    model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="random_forest",
        use_smote=True,
        enable_grid_search=False,
        random_state=0,
    )
    model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="xgboost",
        use_smote=True,
        enable_grid_search=False,
        random_state=0,
    )

    assert sum("[SMOTE]" in w for w in warnings) == 1
    assert "[SMOTE] Synthetic oversampling remains enabled in evidence/paper mode by explicit configuration;" in str(
        getattr(app_config, "RUNTIME_SMOTE_WARNING_LAST", "")
    )


def test_split_cache_notice_is_emitted_once_per_run(monkeypatch):
    X, y = _imbalanced_data()
    infos: list[str] = []

    def capture_info(msg: str, *args, **kwargs) -> None:
        infos.append(str(msg))

    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_CACHE_NOTICE_EMITTED", False, raising=False)
    monkeypatch.setattr(model_trainer_factory.du, "print_info", capture_info)

    model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="random_forest",
        enable_grid_search=False,
        random_state=0,
    )
    model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="xgboost",
        enable_grid_search=False,
        random_state=0,
    )

    assert sum("Reusing cached train/test partition" in m for m in infos) == 1


def test_split_cache_stores_compact_indices_and_rebuilds_current_features(monkeypatch):
    X, y = _imbalanced_data()
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "compact_split_cache", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_SMOTE_OVERSAMPLING", False, raising=False)
    monkeypatch.setattr(model_trainer_factory, "_export_split_audit", lambda **_kwargs: None)
    model_trainer_factory.reset_runtime_training_caches()

    first = model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="random_forest",
        enable_grid_search=False,
        random_state=0,
    )
    cache_entries = model_trainer_factory._runtime_training_state()["split_cache"]
    cached = next(iter(cache_entries.values()))

    assert set(cached) == {"train_index", "test_index", "split_algorithm"}
    assert len(cached["train_index"]) == len(first["sample_ids_train"])
    assert len(cached["test_index"]) == len(first["sample_ids_test"])

    X_with_new_column = X.copy()
    X_with_new_column[6] = np.arange(len(X))
    second = model_trainer_factory.train_model_factory(
        X_with_new_column,
        y,
        model_type="random_forest",
        enable_grid_search=False,
        random_state=0,
    )

    assert second["sample_ids_train"] == first["sample_ids_train"]
    assert second["sample_ids_test"] == first["sample_ids_test"]


def test_split_size_notice_is_emitted_once_per_run(monkeypatch):
    X, y = _imbalanced_data()
    infos: list[str] = []

    def capture_info(msg: str, *args, **kwargs) -> None:
        infos.append(str(msg))

    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_SIZE_NOTICE_EMITTED", False, raising=False)
    monkeypatch.setattr(model_trainer_factory.du, "print_info", capture_info)

    model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="random_forest",
        enable_grid_search=False,
        random_state=0,
    )
    model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="xgboost",
        enable_grid_search=False,
        random_state=0,
    )

    assert sum("[SPLIT] Train size:" in m for m in infos) == 1


def test_smote_default_policy_skips_in_evidence_mode(monkeypatch):
    X, y = _imbalanced_data()
    call_tracker = {"called": False}

    def fake_apply_smote(X_train, y_train, random_state):
        call_tracker["called"] = True
        return X_train, y_train

    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_MODE", True, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_SMOTE_OVERSAMPLING", True, raising=False)
    monkeypatch.setattr(app_config, "DISABLE_SMOTE_IN_EVIDENCE_MODE", True, raising=False)
    monkeypatch.setattr(model_trainer_factory, "apply_smote", fake_apply_smote)

    model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="logistic_regression",
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


def test_train_model_factory_uses_random_split_when_stratify_impossible(monkeypatch) -> None:
    """A class with a single global sample cannot be stratified; training must not crash."""
    monkeypatch.setattr(app_config, "AUTO_ADJUST_TRAIN_TEST_SPLIT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "stratify_singleton_test", raising=False)
    model_trainer_factory.reset_runtime_training_caches()
    X = pd.DataFrame(np.random.randn(40, 3))
    y = pd.Series([0] * 39 + [1])
    result = model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="random_forest",
        enable_grid_search=False,
        random_state=0,
    )
    assert "predictions" in result
    assert len(result["y_test"]) >= 1


def test_balanced_split_path_when_class_has_single_sample(monkeypatch) -> None:
    """AUTO_ADJUST split path must tolerate singleton-class cohorts."""
    monkeypatch.setattr(app_config, "AUTO_ADJUST_TRAIN_TEST_SPLIT", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "balanced_singleton_test", raising=False)
    model_trainer_factory.reset_runtime_training_caches()
    X = pd.DataFrame(np.random.randn(35, 2))
    y = pd.Series([0] * 34 + [1])
    result = model_trainer_factory.train_model_factory(
        X,
        y,
        model_type="random_forest",
        enable_grid_search=False,
        random_state=1,
    )
    assert "predictions" in result


# --- Runtime split defaults ---


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


# --- Split audit export ---


def _split_audit_make_frame(n_samples: int = 40) -> tuple[pd.DataFrame, pd.Series]:
    X, y = make_classification(
        n_samples=n_samples,
        n_features=6,
        n_informative=5,
        n_redundant=0,
        n_classes=3,
        random_state=7,
    )
    index = list(range(1000, 1000 + n_samples))
    return pd.DataFrame(X, index=index), pd.Series(y, index=index)


def test_split_audit_exported_in_paper_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Paper mode should export split audit and split hash."""
    features_df, labels = _split_audit_make_frame(36)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "testrun_split", raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", False, raising=False)
    sha_values = [f"{i:064x}"[-64:] for i in range(len(features_df))]
    meta_df = pd.DataFrame(
        {
            "sample_id": features_df.index.tolist(),
            "sha256": sha_values,
            "family_id": [1] * len(features_df),
            "family_name": ["fam"] * len(features_df),
        }
    )
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", meta_df, raising=False)

    result = model_trainer_factory.train_model_factory(
        features_df=features_df,
        labels=labels,
        model_type="logistic_regression",
        cross_validate=False,
        enable_grid_search=False,
        use_smote=False,
    )
    assert isinstance(result, dict)
    split_hash = getattr(app_config, "RUNTIME_SPLIT_HASH", "")
    split_path = getattr(app_config, "RUNTIME_SPLIT_AUDIT_PATH", "")
    assert isinstance(split_hash, str) and len(split_hash) == 64
    assert Path(split_path).exists()
    audit_df = pd.read_csv(split_path)
    assert "overlap_flag" in audit_df.columns
    assert "duplicate_sha_group_across_splits" in audit_df.columns
    assert "sha256_overlap_count" in audit_df.columns
    assert "sha256_overlap_across_split_flag" in audit_df.columns
    assert int(audit_df["sha256_overlap_count"].iloc[0]) == 0
    assert int(audit_df["sha256_overlap_across_split_flag"].iloc[0]) == 0
    # No package-name metadata is supplied.  The lineage ledger must therefore
    # fall back to the distinct SHA-256 values, rather than grouping every
    # missing package under a literal ``None``/``nan`` token.
    assert audit_df["split_lineage_group_id"].nunique() == len(audit_df)


def test_split_audit_invalid_sha_fails_in_paper_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid SHA values should hard-fail paper-mode split audit export."""
    features_df, labels = _split_audit_make_frame(30)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "testrun_badsha", raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", False, raising=False)
    meta_df = pd.DataFrame(
        {
            "sample_id": features_df.index.tolist(),
            "sha256": ["bad_sha"] * len(features_df),
        }
    )
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", meta_df, raising=False)

    with pytest.raises(RuntimeError):
        model_trainer_factory.train_model_factory(
            features_df=features_df,
            labels=labels,
            model_type="logistic_regression",
            cross_validate=False,
            enable_grid_search=False,
            use_smote=False,
        )


def test_split_audit_handles_sample_id_as_index_and_column(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Split audit should tolerate metadata with sample_id as index and column."""
    features_df, labels = _split_audit_make_frame(36)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "testrun_idxcol", raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", False, raising=False)
    model_trainer_factory.reset_runtime_training_caches()

    meta_df = pd.DataFrame(
        {
            "sample_id": features_df.index.tolist(),
            "sha256": [f"{i:064x}"[-64:] for i in range(len(features_df))],
        }
    ).set_index("sample_id", drop=False)
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", meta_df, raising=False)

    result = model_trainer_factory.train_model_factory(
        features_df=features_df,
        labels=labels,
        model_type="logistic_regression",
        cross_validate=False,
        enable_grid_search=False,
        use_smote=False,
    )
    assert isinstance(result, dict)


def test_split_audit_uses_pre_smote_ids_in_paper_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Paper split audit should validate pre-SMOTE IDs, not synthetic rows."""
    features_df, labels = _split_audit_make_frame(48)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "testrun_presmote", raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", False, raising=False)
    model_trainer_factory.reset_runtime_training_caches()
    meta_df = pd.DataFrame(
        {
            "sample_id": features_df.index.tolist(),
            "sha256": [f"{i:064x}"[-64:] for i in range(len(features_df))],
            "family_id": [1] * len(features_df),
            "family_name": ["fam"] * len(features_df),
        }
    )
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", meta_df, raising=False)

    result = model_trainer_factory.train_model_factory(
        features_df=features_df,
        labels=labels,
        model_type="random_forest",
        cross_validate=False,
        enable_grid_search=False,
        use_smote=True,
    )
    assert isinstance(result, dict)
    split_path = Path(str(getattr(app_config, "RUNTIME_SPLIT_AUDIT_PATH", "")))
    assert split_path.exists()


def test_split_audit_cache_isolated_per_run_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Identical reruns should still emit a run-scoped split audit for each run."""
    features_df, labels = _split_audit_make_frame(36)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", False, raising=False)
    model_trainer_factory.reset_runtime_training_caches()
    meta_df = pd.DataFrame(
        {
            "sample_id": features_df.index.tolist(),
            "sha256": [f"{i:064x}"[-64:] for i in range(len(features_df))],
            "family_id": [1] * len(features_df),
            "family_name": ["fam"] * len(features_df),
        }
    )
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", meta_df, raising=False)

    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "run_a", raising=False)
    model_trainer_factory.train_model_factory(
        features_df=features_df,
        labels=labels,
        model_type="logistic_regression",
        cross_validate=False,
        enable_grid_search=False,
        use_smote=False,
    )
    path_a = Path(str(getattr(app_config, "RUNTIME_SPLIT_AUDIT_PATH", "")))

    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "run_b", raising=False)
    model_trainer_factory.train_model_factory(
        features_df=features_df,
        labels=labels,
        model_type="logistic_regression",
        cross_validate=False,
        enable_grid_search=False,
        use_smote=False,
    )
    path_b = Path(str(getattr(app_config, "RUNTIME_SPLIT_AUDIT_PATH", "")))

    assert path_a.name == "split_freeze_headline_run_a.csv"
    assert path_b.name == "split_freeze_headline_run_b.csv"
    assert path_a.exists()
    assert path_b.exists()


def test_headline_split_audit_is_model_agnostic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    features_df, labels = _split_audit_make_frame(36)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "headline_shared", raising=False)
    model_trainer_factory.reset_runtime_training_caches()
    meta_df = pd.DataFrame(
        {
            "sample_id": features_df.index.tolist(),
            "sha256": [f"{i:064x}"[-64:] for i in range(len(features_df))],
            "family_id": [1] * len(features_df),
            "family_name": ["fam"] * len(features_df),
        }
    )
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", meta_df, raising=False)

    model_trainer_factory.train_model_factory(
        features_df=features_df,
        labels=labels,
        model_type="random_forest",
        cross_validate=False,
        enable_grid_search=False,
        use_smote=False,
    )

    meta = getattr(app_config, "RUNTIME_HEADLINE_SPLIT_METADATA", None)
    assert isinstance(meta, dict)
    assert meta.get("split_model_written_for") == "headline_shared_split"
    audit_path = Path(str(meta.get("split_audit_path", "")))
    audit = pd.read_csv(audit_path)
    assert audit["model"].nunique() == 1
    assert str(audit["model"].iloc[0]) == "headline_shared_split"


def test_ablation_split_audit_is_shared_across_models(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Equivalent ablation fits should reference one persisted split ledger."""
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "ablation_shared", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_LEDGER_INDEX", {}, raising=False)
    model_trainer_factory.reset_runtime_training_caches()
    metadata = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "sha256": [f"{value:064x}"[-64:] for value in range(1, 5)],
        }
    )
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", metadata, raising=False)

    common = {
        "split_cache_key": ("same-cohort",),
        "sample_ids_train": [1, 2, 3],
        "sample_ids_test": [4],
        "random_state": 42,
        "active_class_count": 2,
        "label_field": "family_id",
        "label_target_slug": "family_id",
        "feature_set_token": "vendor_no_parsed_family",
    }
    model_trainer_factory._export_split_audit(model_type="random_forest", **common)  # pylint: disable=protected-access
    model_trainer_factory._export_split_audit(model_type="xgboost", **common)  # pylint: disable=protected-access

    ledgers = list(tmp_path.glob("split_freeze_ablation__*.csv"))
    assert len(ledgers) == 1
    assert "__shared__" in ledgers[0].name
    index = getattr(app_config, "RUNTIME_SPLIT_LEDGER_INDEX")
    assert isinstance(index, dict)
    rf = index[("ablation_shared", "vendor_no_parsed_family", "family_id", "random_forest")]
    xgb = index[("ablation_shared", "vendor_no_parsed_family", "family_id", "xgboost")]
    assert rf["split_audit_path"] == xgb["split_audit_path"]


def test_temporal_holdout_summary_records_dropped_family_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    features_df = pd.DataFrame(
        np.random.randn(6, 3),
        index=[1001, 1002, 1003, 1004, 1005, 1006],
    )
    labels = pd.Series(["1", "1", "2", "1", "2", "3"], index=features_df.index)
    labels.attrs["label_name_map"] = {"1": "Irata", "2": "Applite", "3": "Zanubis"}

    meta_df = pd.DataFrame(
        {
            "sample_id": features_df.index.tolist(),
            "effective_first_seen_at_utc": [
                "2020-01-01T00:00:00Z",
                "2021-01-01T00:00:00Z",
                "2022-01-01T00:00:00Z",
                "2024-01-01T00:00:00Z",
                "2024-06-01T00:00:00Z",
                "2025-01-01T00:00:00Z",
            ],
        }
    )
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", meta_df, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_PROFILE_ID", "malicious_temporal_test", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_TEMPORAL_SPLIT_SUMMARY", None, raising=False)

    encoded = np.array([0, 0, 1, 0, 1, 2], dtype=int)
    temporal = model_trainer_factory._build_temporal_holdout_split(  # pylint: disable=protected-access
        features_df,
        encoded,
        labels=labels,
        quiet_train=True,
    )

    assert temporal is not None
    summary = getattr(app_config, "RUNTIME_TEMPORAL_SPLIT_SUMMARY", {}) or {}
    assert summary.get("test_rows_dropped_unseen_train_classes") == 1
    assert summary.get("test_rows_dropped_unseen_train_class_families") == {"Zanubis": 1}
