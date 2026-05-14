"""Tests for model config snapshot export helper."""

from __future__ import annotations

import json
from pathlib import Path

from config import app_config
import main


def test_export_model_config_snapshot_writes_artifacts(monkeypatch, tmp_path: Path) -> None:
    """Model config snapshot helper should write run-scoped and latest JSON artifacts."""
    output_root = tmp_path / "output"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RANDOM_STATE", 42, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", True, raising=False)
    monkeypatch.setattr(app_config, "CV_FOLDS", 5, raising=False)
    monkeypatch.setattr(app_config, "CV_REPEATS", 1, raising=False)

    model_results = {
        "logistic_regression": {
            "metadata": {"params": {"C": 1.0, "solver": "lbfgs"}},
            "evaluation": {"macro_f1_score": 0.79, "accuracy": 0.93, "train_time": 12.1},
            "cv_score_mean": 0.77,
        }
    }
    artifacts: list[str] = []
    manifest_context: dict[str, str] = {}

    out_path = main._export_model_config_snapshot(  # pylint: disable=protected-access
        run_id="r1",
        model_results=model_results,
        artifact_list=artifacts,
        manifest_context=manifest_context,
    )

    assert out_path is not None
    assert Path(out_path).exists()
    latest = output_root / "diagnostics" / "model_config_snapshot.latest.json"
    assert latest.exists()
    payload = json.loads(Path(out_path).read_text(encoding="utf-8"))
    assert payload["run_id"] == "r1"
    assert "logistic_regression" in payload["models"]
    assert "model_config_hash" in manifest_context
    assert payload["model_contract_hash"] == manifest_context["model_config_hash"]
    assert payload["model_contract_hash_basis"] == "config_only_no_run_id_no_metrics"


def test_model_config_hash_is_stable_for_same_config(monkeypatch, tmp_path: Path) -> None:
    """Hash should ignore run_id and evaluation metrics and track only model config contract."""
    output_root = tmp_path / "output"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RANDOM_STATE", 42, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", True, raising=False)
    monkeypatch.setattr(app_config, "CV_FOLDS", 4, raising=False)
    monkeypatch.setattr(app_config, "CV_REPEATS", 1, raising=False)

    model_results_a = {
        "logistic_regression": {
            "metadata": {"params": {"C": 1.0, "solver": "lbfgs"}},
            "evaluation": {"macro_f1_score": 0.70, "accuracy": 0.90, "train_time": 10.0},
            "cv_score_mean": 0.70,
        }
    }
    model_results_b = {
        "logistic_regression": {
            "metadata": {"params": {"C": 1.0, "solver": "lbfgs"}},
            "evaluation": {"macro_f1_score": 0.99, "accuracy": 0.99, "train_time": 999.0},
            "cv_score_mean": 0.99,
        }
    }
    artifacts_a: list[str] = []
    artifacts_b: list[str] = []
    manifest_a: dict[str, str] = {}
    manifest_b: dict[str, str] = {}

    main._export_model_config_snapshot(  # pylint: disable=protected-access
        run_id="run_a",
        model_results=model_results_a,
        artifact_list=artifacts_a,
        manifest_context=manifest_a,
    )
    main._export_model_config_snapshot(  # pylint: disable=protected-access
        run_id="run_b",
        model_results=model_results_b,
        artifact_list=artifacts_b,
        manifest_context=manifest_b,
    )

    assert manifest_a["model_config_hash"] == manifest_b["model_config_hash"]


def test_export_model_config_snapshot_tolerates_none_cv_settings(monkeypatch, tmp_path: Path) -> None:
    """Snapshot export must not use bare ``int(None)`` on optional CV config."""
    output_root = tmp_path / "output"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RANDOM_STATE", None, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_CROSS_VALIDATION", True, raising=False)
    monkeypatch.setattr(app_config, "CV_FOLDS", None, raising=False)
    monkeypatch.setattr(app_config, "CV_REPEATS", None, raising=False)

    model_results = {
        "rf": {
            "metadata": {"params": {"n_estimators": 10}},
            "evaluation": {"macro_f1_score": 0.5, "accuracy": 0.5, "train_time": 1.0},
            "cv_score_mean": 0.5,
        }
    }
    artifacts: list[str] = []
    manifest_context: dict[str, str] = {}

    out_path = main._export_model_config_snapshot(
        run_id="r_none_cv",
        model_results=model_results,
        artifact_list=artifacts,
        manifest_context=manifest_context,
    )
    assert out_path is not None
    payload = json.loads(Path(out_path).read_text(encoding="utf-8"))
    assert payload["random_seed"] == 42
    assert payload["cv"]["folds"] == 5
    assert payload["cv"]["repeats"] == 1

    monkeypatch.setattr(app_config, "CV_FOLDS", 1, raising=False)
    out_path2 = main._export_model_config_snapshot(
        run_id="r_fold_one",
        model_results=model_results,
        artifact_list=[],
        manifest_context={},
    )
    payload2 = json.loads(Path(out_path2).read_text(encoding="utf-8"))
    assert payload2["cv"]["folds"] == 2
