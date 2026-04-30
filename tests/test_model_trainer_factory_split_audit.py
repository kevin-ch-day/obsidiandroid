"""Tests for split-audit export behavior in model trainer factory."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sklearn.datasets import make_classification

from config import app_config
from ml_classification.training import model_trainer_factory


def _make_frame(n_samples: int = 40) -> tuple[pd.DataFrame, pd.Series]:
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
    features_df, labels = _make_frame(36)
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


def test_split_audit_invalid_sha_fails_in_paper_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid SHA values should hard-fail paper-mode split audit export."""
    features_df, labels = _make_frame(30)
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
    features_df, labels = _make_frame(36)
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
    features_df, labels = _make_frame(48)
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
    features_df, labels = _make_frame(36)
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

    assert path_a.name == "split_freeze_audit_run_a.csv"
    assert path_b.name == "split_freeze_audit_run_b.csv"
    assert path_a.exists()
    assert path_b.exists()
