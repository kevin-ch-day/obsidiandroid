"""Small, database-free integration check for publication integrity contracts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

from config import app_config
from obsidiandroid.diagnostics.research_validity.paper_claim_audit import write_paper_claim_audit_md
from obsidiandroid.evaluation import ml_comparator_summary, ml_eval_engine
from obsidiandroid.features.vectorization import feature_vector_builder
from obsidiandroid.modeling import model_trainer_factory, pipeline_core
from obsidiandroid.orchestration import methodology_artifacts
from obsidiandroid.pipeline import stage_permission_trends_report


class _PredictedLabels:
    def __init__(self, predictions: list[int], feature_columns: list[str]) -> None:
        self._predictions = np.asarray(predictions)
        self.feature_names_in_ = np.asarray(feature_columns, dtype=object)

    def predict(self, _features):  # type: ignore[no-untyped-def]
        return self._predictions


def test_publication_integrity_smoke_exports_consistent_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Exercise the final integrity gates without a database or full pipeline."""
    run_id = "research_integrity_smoke_v1"
    diagnostics_dir = tmp_path / "output" / "runs" / run_id / "diagnostics"
    diagnostics_dir.mkdir(parents=True)

    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_TRAINING_STATE", {}, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_LABEL_DERIVED_VENDOR_FEATURES", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True, raising=False)

    monkeypatch.setattr(feature_vector_builder, "_select_top_vendors", lambda *_a, **_k: ["engine_a"])
    monkeypatch.setattr(feature_vector_builder, "_export_pre_gate_vendor_scores", lambda **_k: None)
    monkeypatch.setattr(feature_vector_builder, "_export_vendor_gate_debug", lambda **_k: "")
    raw_features = feature_vector_builder.build_feature_vector(
        weights_df=pd.DataFrame({"Vendor": ["engine_a"], "Leakage Safe Score": [0.9]}),
        parsed_vendor_data={
            "engine_a": pd.DataFrame(
                {
                    "sample_id": [1, 2, 3, 4],
                    "Parsed Family": ["a", "a", "b", "b"],
                    "Threat Class": ["t", "t", "t", "t"],
                    "Malware Type": ["m", "m", "m", "m"],
                }
            )
        },
        extra_features_df=pd.DataFrame(
            {
                "sample_id": [1, 2, 3, 4],
                "perm__internet": [1, 0, 1, 0],
                "meta__malicious_ratio": [0.9, 0.8, 0.7, 0.6],
            }
        ),
        top_k=1,
        verbose=False,
    )
    final_features = pipeline_core._prune_potential_leakage_features(
        raw_features,
        pd.Series([0, 0, 1, 1], index=raw_features.index),
    )
    assert final_features.shape[1] > 0
    assert not any(
        token in str(column).lower()
        for column in final_features.columns
        for token in ("parsed_family", "threat_class", "malware_type", "suggested_threat_label")
    )

    methodology_artifacts.export_feature_contract(final_features, run_id, str(diagnostics_dir))
    methodology_artifacts.export_leakage_assessment(final_features, run_id, str(diagnostics_dir))
    contract_path = diagnostics_dir / f"feature_contract_{run_id}.json"
    columns_path = diagnostics_dir / f"feature_columns_{run_id}.csv"
    leakage_path = diagnostics_dir / f"leakage_assessment_{run_id}.txt"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    leakage = leakage_path.read_text(encoding="utf-8")
    assert contract["run_id"] == run_id
    assert contract["classification_surface"] == "label_independent"
    assert contract["publication_gate"] == "PASS"
    assert contract["prohibited_semantic_columns"] == []
    assert pd.read_csv(columns_path)["feature_column"].tolist() == list(final_features.columns)
    assert "publication_gate=PASS" in leakage

    metadata = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "sha256": [f"{value:064x}" for value in range(1, 5)],
            "family_id": [10, 10, 20, 20],
            "family_canonical": ["A", "A", "B", "B"],
        }
    )
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", metadata, raising=False)
    model_trainer_factory._export_split_audit(  # pylint: disable=protected-access
        split_cache_key=("integrity", run_id),
        sample_ids_train=[1, 2],
        sample_ids_test=[3, 4],
        random_state=7,
        model_type="random_forest",
        active_class_count=2,
        label_field="family_id",
        label_target_slug="family_id",
        feature_set_token="full_fused",
    )
    split_path = diagnostics_dir / f"split_freeze_headline_{run_id}.csv"
    split = pd.read_csv(split_path)
    assert split["run_id"].eq(run_id).all()
    assert split["train_sample_hash"].nunique() == split["test_sample_hash"].nunique() == 1

    captured_confusion: dict[str, object] = {}

    def _capture_confusion(**kwargs):  # type: ignore[no-untyped-def]
        name = str(kwargs["model_name"])
        path = diagnostics_dir / f"confusion_matrix_metadata_{name}_{run_id}.json"
        payload = {
            "run_id": run_id,
            "model": name,
            "class_labels": list(kwargs["class_labels"]),
            "matrix": np.asarray(kwargs["cm"]).tolist(),
        }
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        captured_confusion[name] = payload
        return str(path)

    monkeypatch.setattr(ml_eval_engine.export_manager, "export_confusion_matrix", _capture_confusion)
    label_encoder = LabelEncoder().fit([10, 20])
    x_test = final_features.loc[[3, 4]]
    y_test = np.asarray([0, 1])
    rf_model = _PredictedLabels([0, 1], list(final_features.columns))
    xgb_model = _PredictedLabels([0, 0], list(final_features.columns))
    rf_eval = ml_eval_engine.evaluate_model_performance(
        rf_model,
        x_test,
        y_test,
        label_encoder,
        "random_forest",
        verbose=False,
    )
    xgb_eval = ml_eval_engine.evaluate_model_performance(
        xgb_model,
        x_test,
        y_test,
        label_encoder,
        "xgboost",
        verbose=False,
    )
    assert rf_eval["evaluation_label_hash"] == xgb_eval["evaluation_label_hash"]
    assert rf_eval["evaluation_labels"] == xgb_eval["evaluation_labels"] == [0, 1]
    assert rf_eval["num_confusion_labels"] == xgb_eval["num_confusion_labels"] == 2
    assert captured_confusion["random_forest"]["class_labels"] == captured_confusion["xgboost"]["class_labels"]

    monkeypatch.setattr(
        app_config,
        "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH",
        contract["feature_column_hash"],
        raising=False,
    )
    comparison = ml_comparator_summary.compare_model_performance(
        {
            "random_forest": {"model": rf_model, "evaluation": rf_eval},
            "xgboost": {"model": xgb_model, "evaluation": xgb_eval},
        }
    )
    comparison_path = diagnostics_dir / f"model_comparison_summary_{run_id}.csv"
    comparison.to_csv(comparison_path, index=False)
    assert comparison["split_hash"].nunique() == 1
    assert comparison["train_sample_hash"].nunique() == 1
    assert comparison["test_sample_hash"].nunique() == 1
    assert comparison["evaluation_label_hash"].nunique() == 1
    assert comparison["evaluation_label_count"].eq(2).all()
    assert comparison["fit_feature_column_hash"].eq(contract["feature_column_hash"]).all()

    metric_config_path = diagnostics_dir / f"metric_configuration_{run_id}.json"
    metric_config_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "metric_label_universe": rf_eval["evaluation_labels"],
                "evaluation_label_hash": rf_eval["evaluation_label_hash"],
                "confusion_label_universe": rf_eval["class_labels"],
                "split_hash": split.loc[0, "split_hash"],
            },
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    (diagnostics_dir / "feature_set_ablation_summary.csv").write_text(
        f"status,run_id\nablation_summary_unavailable_or_empty,{run_id}\n",
        encoding="utf-8",
    )
    claim_path = write_paper_claim_audit_md(
        diagnostics_dir=diagnostics_dir,
        manifest={},
        manifest_context={},
        run_id=run_id,
    )
    claim_text = claim_path.read_text(encoding="utf-8")
    assert "status=unavailable; reason=ablation_disabled" in claim_text
    assert "full_fused=" not in claim_text
    assert "annual_permission_trend_status=NOT_AVAILABLE" in claim_text

    correlation = stage_permission_trends_report._spearman_similarity_details(  # pylint: disable=protected-access
        np.asarray([0.0, 0.0]), np.asarray([0.0, 1.0])
    )
    correlation_path = diagnostics_dir / f"permission_similarity_{run_id}.csv"
    pd.DataFrame([{"run_id": run_id, **correlation}]).to_csv(correlation_path, index=False)
    assert correlation["spearman_correlation"] is None
    assert correlation["correlation_status"] == "constant_input"
    assert correlation["left_profile_constant"] is True
    assert pd.Series([correlation["spearman_correlation"]]).dropna().empty

    artifact_paths = [
        contract_path,
        columns_path,
        leakage_path,
        split_path,
        comparison_path,
        metric_config_path,
        claim_path,
        correlation_path,
        diagnostics_dir / f"confusion_matrix_metadata_random_forest_{run_id}.json",
        diagnostics_dir / f"confusion_matrix_metadata_xgboost_{run_id}.json",
    ]
    assert all(path.is_file() for path in artifact_paths)
    assert run_id in "\n".join(path.read_text(encoding="utf-8") for path in artifact_paths)
    print(f"INTEGRATION_ARTIFACT_ROOT={diagnostics_dir}")
    print(f"INTEGRATION_RUN_ID={run_id}")
