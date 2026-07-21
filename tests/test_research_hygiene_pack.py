"""Tests for holdout calibration and Core Results artifact mapping."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics.core_results_artifact_map import (
    compose_core_results_artifact_map,
    map_core_results_artifacts,
)
from obsidiandroid.reporting.holdout_calibration_report import (
    build_calibration_tables,
    build_split_class_accounting,
    compose_holdout_calibration_report,
)


def test_split_class_accounting_train_only() -> None:
    split = pd.DataFrame(
        [
            {"split_role": "train", "family_canonical": "A"},
            {"split_role": "train", "family_canonical": "B"},
            {"split_role": "train", "family_canonical": "C"},
            {"split_role": "test", "family_canonical": "A"},
            {"split_role": "test", "family_canonical": "B"},
        ]
    )
    out = build_split_class_accounting(split, visible_family_count=10)
    assert out["training_target_classes"] == 3
    assert out["held_out_evaluated_classes"] == 2
    assert out["train_only_classes"] == 1
    assert out["train_only_family_canonical"] == ["C"]
    assert out["reconciles_training_minus_heldout"] is True


def test_calibration_metrics_basic() -> None:
    pred = pd.DataFrame(
        [
            {"true_label_id": 1, "predicted_label_id": 1, "true_label_name": "A", "confidence": 0.9},
            {"true_label_id": 1, "predicted_label_id": 1, "true_label_name": "A", "confidence": 0.8},
            {"true_label_id": 2, "predicted_label_id": 3, "true_label_name": "B", "confidence": 0.95},
            {"true_label_id": 2, "predicted_label_id": 2, "true_label_name": "B", "confidence": 0.6},
        ]
    )
    support = {"A": 100, "B": 10}
    reliability, tiers, metrics = build_calibration_tables(pred, support, n_bins=4)
    assert metrics["n_predictions"] == 4
    assert 0.0 <= float(metrics["ece_equal_width_10"]) <= 1.0
    assert 0.0 <= float(metrics["brier_top1_correctness"]) <= 1.0
    assert not reliability.empty
    assert not tiers.empty


def test_compose_holdout_and_core_map(tmp_path: Path) -> None:
    run_id = "hyg_fix"
    run_root = tmp_path / "run"
    diag = run_root / "diagnostics"
    models = run_root / "models" / "logistic_regression"
    bundles = run_root / "bundles" / "permission_trends" / "tables"
    for path in (diag, models, bundles, run_root / "conf_matrices"):
        path.mkdir(parents=True)
    (run_root / "run_manifest.json").write_text(json.dumps({"run_status": "complete"}), encoding="utf-8")
    (diag / "run_observability_summary.json").write_text(
        json.dumps({"visible_family_count": 5, "run_status": "complete"}),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "sample_id": 1,
                "true_label_id": 1,
                "predicted_label_id": 1,
                "true_label_name": "A",
                "predicted_label_name": "A",
                "confidence": 0.99,
            },
            {
                "sample_id": 2,
                "true_label_id": 2,
                "predicted_label_id": 3,
                "true_label_name": "B",
                "predicted_label_name": "C",
                "confidence": 0.91,
            },
        ]
    ).to_csv(diag / f"headline_test_predictions_{run_id}.csv", index=False)
    pd.DataFrame(
        [
            {"sample_id": 1, "family_canonical": "A", "split_role": "train"},
            {"sample_id": 2, "family_canonical": "B", "split_role": "train"},
            {"sample_id": 3, "family_canonical": "C", "split_role": "train"},
            {"sample_id": 4, "family_canonical": "A", "split_role": "test"},
            {"sample_id": 5, "family_canonical": "B", "split_role": "test"},
        ]
    ).to_csv(diag / f"split_freeze_headline_{run_id}.csv", index=False)
    (models / "logistic_regression_classifier_model_metadata.json").write_text("{}", encoding="utf-8")
    pd.DataFrame({"a": [1]}).to_csv(diag / f"model_comparison_summary_{run_id}.csv", index=False)
    pd.DataFrame({"a": [1]}).to_csv(
        bundles / f"permission_prevalence_by_type_{run_id}.csv", index=False
    )
    (diag / f"label_contract_{run_id}.md").write_text("x", encoding="utf-8")
    pd.DataFrame({"a": [1]}).to_csv(diag / f"aligned_labels_{run_id}.csv", index=False)
    pd.DataFrame({"a": [1]}).to_csv(diag / "top_confusion_pairs.csv", index=False)
    (diag / f"modality_method_contract_{run_id}.json").write_text("{}", encoding="utf-8")
    (diag / f"feature_column_survival_{run_id}.csv").write_text("feature_name\nx\n", encoding="utf-8")

    cal = compose_holdout_calibration_report(run_root=run_root, run_id=run_id)
    assert cal["split_class_accounting"]["train_only_classes"] == 1
    assert cal["metrics"]["n_predictions"] == 2
    assert Path(cal["report_markdown"]).is_file()

    mapped = map_core_results_artifacts(run_root, run_id)
    assert "prediction" in set(mapped["core_table"])
    core = compose_core_results_artifact_map(run_root=run_root, run_id=run_id)
    assert core["writes_to_core"] is False
    assert core["present_count"] >= 6
    assert Path(core["report_markdown"]).is_file()
