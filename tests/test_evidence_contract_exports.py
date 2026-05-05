"""Evidence contract: split ledgers, confusion-matrix resolution, headline test tables."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from sklearn.datasets import make_classification

from config import app_config
from ml_classification.training import model_trainer_factory
from obsidiandroid.diagnostics import headline_evaluation_export
from obsidiandroid.pipeline import stage_manifest


def test_headline_split_ledger_unchanged_after_ablation_ledger_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ablation split ledgers must not overwrite the headline CSV bytes on disk."""
    diag = tmp_path / "diag"
    diag.mkdir()
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diag), raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "out"), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "ledger_demo", raising=False)
    model_trainer_factory.reset_runtime_training_caches()

    X, y = make_classification(
        n_samples=80, n_features=8, n_informative=6, n_redundant=0, n_classes=2, random_state=3
    )
    feats = pd.DataFrame(X, index=list(range(5000, 5000 + len(X))))
    labels_a = pd.Series(y, index=feats.index, name="col_a")

    sid = feats.index.tolist()
    meta = pd.DataFrame(
        {
            "sample_id": sid,
            "sha256": [f"{i:064x}" for i in range(len(sid))],
            "family_id": [1] * len(sid),
        }
    )
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", meta, raising=False)

    model_trainer_factory.train_model_factory(
        features_df=feats,
        labels=labels_a,
        model_type="logistic_regression",
        cross_validate=False,
        enable_grid_search=False,
        use_smote=False,
    )
    headline = diag / "split_freeze_headline_ledger_demo.csv"
    assert headline.exists()
    frozen_headline = headline.read_bytes()

    y_b = np.where(y == 0, 2, 0).astype(int)
    labels_b = pd.Series(y_b, index=feats.index, name="col_b")
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_FEATURE_SET_NAME", "matrix", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EXPERIMENT_ID", "matrix__lt_target", raising=False)

    model_trainer_factory.train_model_factory(
        features_df=feats,
        labels=labels_b,
        model_type="logistic_regression",
        cross_validate=False,
        enable_grid_search=False,
        use_smote=False,
    )
    assert headline.read_bytes() == frozen_headline
    assert list(diag.glob("split_freeze_ablation__*.csv"))


def test_headline_split_metadata_matches_embedded_csv_hash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """RUNTIME_HEADLINE_SPLIT_METADATA.split_hash must match the headline ledger column."""
    diag = tmp_path / "diag2"
    diag.mkdir()
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diag), raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "out"), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "hash_demo", raising=False)
    model_trainer_factory.reset_runtime_training_caches()

    X, y = make_classification(
        n_samples=60, n_features=6, n_informative=5, n_redundant=0, n_classes=3, random_state=9
    )
    feats = pd.DataFrame(X, index=list(range(7000, 7000 + len(X))))
    labels = pd.Series(y, index=feats.index, name="family_id")
    sid = feats.index.tolist()
    meta = pd.DataFrame(
        {
            "sample_id": sid,
            "sha256": [f"{i:064x}" for i in range(len(sid))],
            "family_id": [1] * len(sid),
        }
    )
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", meta, raising=False)

    model_trainer_factory.train_model_factory(
        features_df=feats,
        labels=labels,
        model_type="logistic_regression",
        cross_validate=False,
        enable_grid_search=False,
        use_smote=False,
    )
    meta_head = getattr(app_config, "RUNTIME_HEADLINE_SPLIT_METADATA", None)
    assert isinstance(meta_head, dict)
    path = Path(str(meta_head.get("split_audit_path", "")))
    assert path.exists()
    audit = pd.read_csv(path)
    assert audit["split_hash"].nunique() == 1
    assert str(audit["split_hash"].iloc[0]) == str(meta_head.get("split_hash"))


def test_find_primary_confusion_matrix_prefers_primary_alias(tmp_path: Path) -> None:
    """Lexicographic ordering must not beat explicit primary/RF headline filenames."""
    run_root = tmp_path / "runs" / "r1"
    cm_dir = run_root / "conf_matrices"
    cm_dir.mkdir(parents=True)
    (cm_dir / "confusion_matrix_aaa_first_lex.png").write_bytes(b"a")
    (cm_dir / "confusion_matrix_primary.png").write_bytes(b"b")
    chosen = stage_manifest._find_primary_confusion_matrix(  # pylint: disable=protected-access
        run_root=run_root,
        top_model="random_forest",
        evidence_mode=False,
    )
    assert chosen is not None
    assert chosen.name == "confusion_matrix_primary.png"


def test_headline_test_predictions_only_include_eval_split(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Exports must list exactly the held-out test indices (not the full training pool)."""
    X_test = pd.DataFrame({"perm__x": [1.0, 0.0]}, index=[10, 11])
    y_true = np.array([0, 1])
    y_pred = np.array([0, 0])
    enc = MagicMock()
    enc.classes_ = np.array([0, 1])
    enc.inverse_transform.side_effect = lambda arr: np.array([f"cls_{int(x)}" for x in arr])

    model = MagicMock()
    model.predict_proba.return_value = np.array([[0.9, 0.1], [0.6, 0.4]])

    results = {
        "random_forest": {
            "model": model,
            "X_test": X_test,
            "y_test": y_true,
            "label_encoder": enc,
            "evaluation": {"y_true": y_true, "y_pred": y_pred},
        }
    }
    monkeypatch.setattr(
        app_config,
        "RUNTIME_HEADLINE_SPLIT_METADATA",
        {"split_hash": "aa" * 32},
        raising=False,
    )
    monkeypatch.setattr(app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "ff", raising=False)
    monkeypatch.setattr(
        app_config,
        "RUNTIME_SPLIT_SAMPLE_METADATA",
        pd.DataFrame(
            {
                "sample_id": [10, 11, 99],
                "sha256": ["ab" * 32, "cd" * 32, "ef" * 32],
                "type_slug": ["banker", "banker", "rat"],
                "type_slug_expected": ["banker", "adware", "rat"],
            }
        ),
        raising=False,
    )
    pred_p, err_p = headline_evaluation_export.export_headline_test_tables(
        results=results,
        promoted_model_key="random_forest",
        diagnostics_dir=tmp_path,
        run_id="evidence_unit",
        label_field="family_id",
    )
    assert pred_p is not None and err_p is not None
    pred_df = pd.read_csv(pred_p)
    assert sorted(pred_df["sample_id"].tolist()) == [10, 11]
    assert pred_df["split_role"].eq("test").all()
    err_df = pd.read_csv(err_p)
    assert len(err_df) == 1
    assert int(err_df.iloc[0]["sample_id"]) == 11
