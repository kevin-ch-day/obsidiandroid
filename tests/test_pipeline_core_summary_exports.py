"""Tests for model-summary export behavior in pipeline_core."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.orchestration.runtime_reporting import format_population_pipeline_summary_line
from obsidiandroid.modeling import pipeline_core


def test_summarize_models_exports_csv_and_skips_excel_by_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Summary export should default to CSV and avoid hot-path Excel writes."""
    run_id = "20260302T000000Z__testrun"
    output_root = tmp_path / "output"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(
        app_config,
        "RUNTIME_DIAGNOSTICS_DIR",
        str(output_root / "runs" / run_id / "diagnostics"),
        raising=False,
    )
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_MODEL_COMPARISON_CSV_EXPORT", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_MODEL_COMPARISON_EXCEL_EXPORT", False, raising=False)
    monkeypatch.setattr(
        pipeline_core.comparator,
        "compare_model_performance",
        lambda _results: pd.DataFrame(
            [
                {"Model": "logistic_regression", "Macro F1-Score": 0.80},
                {"Model": "random_forest", "Macro F1-Score": 0.75},
            ]
        ),
    )
    monkeypatch.setattr(
        pipeline_core.inspector,
        "generate_classification_summary",
        lambda **_kwargs: None,
    )

    excel_calls = {"count": 0}

    def _fake_export_dataframe_to_excel(**_kwargs):
        excel_calls["count"] += 1
        return "unused.xlsx"

    monkeypatch.setattr(pipeline_core.em, "export_dataframe_to_excel", _fake_export_dataframe_to_excel)

    results = {
        "logistic_regression": {
            "evaluation": {
                "accuracy": 0.90,
                "macro_f1_score": 0.80,
                "confusion_matrix_path": "cm.png",
            }
        },
        "random_forest": {
            "evaluation": {
                "accuracy": 0.88,
                "macro_f1_score": 0.75,
                "confusion_matrix_path": "cm2.png",
            }
        },
    }

    top_model = pipeline_core.summarize_models(results)

    assert top_model == "logistic_regression"
    assert excel_calls["count"] == 0
    summary_csv = output_root / "runs" / run_id / "diagnostics" / f"model_comparison_summary_{run_id}.csv"
    assert summary_csv.exists()


def test_summarize_models_paper_mode_filters_balanced_rf(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Paper-mode summary should keep only RF/XGB/LR rows."""
    run_id = "20260302T000000Z__paper"
    output_root = tmp_path / "output"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(
        app_config,
        "RUNTIME_DIAGNOSTICS_DIR",
        str(output_root / "runs" / run_id / "diagnostics"),
        raising=False,
    )
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_MODEL_COMPARISON_CSV_EXPORT", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_MODEL_COMPARISON_EXCEL_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(
        pipeline_core.comparator,
        "compare_model_performance",
        lambda _results: pd.DataFrame(
            [
                {"Model": "balanced_random_forest", "Macro F1-Score": 0.95},
                {"Model": "random_forest", "Macro F1-Score": 0.90},
                {"Model": "xgboost", "Macro F1-Score": 0.89},
                {"Model": "logistic_regression", "Macro F1-Score": 0.88},
            ]
        ),
    )
    monkeypatch.setattr(
        pipeline_core.inspector,
        "generate_classification_summary",
        lambda **_kwargs: None,
    )

    results = {
        "balanced_random_forest": {"evaluation": {"accuracy": 0.95, "macro_f1_score": 0.95}},
        "random_forest": {"evaluation": {"accuracy": 0.90, "macro_f1_score": 0.90}},
        "xgboost": {"evaluation": {"accuracy": 0.89, "macro_f1_score": 0.89}},
        "logistic_regression": {"evaluation": {"accuracy": 0.88, "macro_f1_score": 0.88}},
    }

    top_model = pipeline_core.summarize_models(results)

    assert top_model == "random_forest"
    summary_csv = output_root / "runs" / run_id / "diagnostics" / f"model_comparison_summary_{run_id}.csv"
    exported = pd.read_csv(summary_csv)
    assert set(exported["Model"].tolist()) == {"random_forest", "xgboost", "logistic_regression"}


def test_run_classifier_pipeline_exports_leakage_pruning_audit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Leakage pruning should emit a reason-coded audit artifact for dropped columns."""
    run_id = "20260321T000000Z__audit"
    output_root = tmp_path / "output"
    diagnostics_dir = output_root / "runs" / run_id / "diagnostics"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_FEATURE_CONTRACT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_LEAKAGE_ASSESSMENT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "GROUP_LOW_SUPPORT_LABELS", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", 1, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_AGGRESSIVE_LEAKAGE_PRUNING", False, raising=False)
    monkeypatch.setattr(
        pipeline_core.distribution_reporter,
        "print_family_distribution",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        pipeline_core.distribution_reporter,
        "apply_min_family_support",
        lambda **kwargs: (kwargs["features_df"], kwargs["labels_df"], 0, 0, []),
    )
    monkeypatch.setattr(
        pipeline_core,
        "train_models",
        lambda *_args, **_kwargs: (
            {"logistic_regression": {"evaluation": {"accuracy": 1.0}}},
            [],
        ),
    )
    monkeypatch.setattr(pipeline_core, "summarize_models", lambda _results: "logistic_regression")
    monkeypatch.setattr(pipeline_core, "promote_default_model", lambda *_args, **_kwargs: None)

    features_df = pd.DataFrame(
        {
            "sample_id": ["101", "102"],
            "signal": [1.0, 2.0],
        },
        index=["101", "102"],
    )
    samples_df = pd.DataFrame(
        {
            "sample_id": [101, 102],
            "family_id": [44, 51],
            "family_canonical": ["Irata", "SpyNote"],
        }
    )

    result = pipeline_core.run_classifier_pipeline(
        features_df=features_df,
        samples_df=samples_df,
        save_model=False,
        models=["logistic_regression"],
    )

    assert "logistic_regression" in result
    audit_path = diagnostics_dir / f"leakage_pruning_audit_{run_id}.csv"
    assert audit_path.exists()
    audit_df = pd.read_csv(audit_path)
    assert "reason_code" in audit_df.columns
    names = audit_df["column_name"].tolist()
    assert "sample_id" in names
    assert "__summary__" in names


def test_export_leakage_pruning_audit_normalizes_missing_run_id(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_LEAKAGE_PRUNING_AUDIT", [], raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", None, raising=False)
    out = pipeline_core._export_leakage_pruning_audit(tmp_path, final_column_count=3)
    assert out == str(tmp_path / "leakage_pruning_audit_unknown.csv")
    assert not (tmp_path / "leakage_pruning_audit_None.csv").exists()


def test_export_label_name_map_run_scoped_uses_global_latest(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)
    labels = pd.Series(["1", "2"])
    labels.attrs["label_name_map"] = {"1": "Irata", "2": "Applite"}

    out = pipeline_core._export_label_name_map(labels, diagnostics_dir)  # pylint: disable=protected-access

    assert out == str(diagnostics_dir / "label_name_map_rid.json")
    assert not (diagnostics_dir / "label_name_map.latest.json").exists()
    assert (output_root / "diagnostics" / "label_name_map.latest.json").exists()


def test_export_leakage_pruning_audit_run_scoped_uses_global_latest(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(app_config, "RUNTIME_LEAKAGE_PRUNING_AUDIT", [], raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)

    out = pipeline_core._export_leakage_pruning_audit(diagnostics_dir, final_column_count=3)  # pylint: disable=protected-access

    assert out == str(diagnostics_dir / "leakage_pruning_audit_rid.csv")
    assert not (diagnostics_dir / "leakage_pruning_audit.latest.csv").exists()
    assert (output_root / "diagnostics" / "leakage_pruning_audit.latest.csv").exists()


def test_export_leakage_pruning_audit_rejects_literal_none_directory(
    monkeypatch,
) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_LEAKAGE_PRUNING_AUDIT", [], raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)
    try:
        pipeline_core._export_leakage_pruning_audit(Path("None"), final_column_count=1)
    except ValueError as exc:
        assert "literal 'None' path" in str(exc)
    else:
        raise AssertionError("expected literal None diagnostics path to be rejected")


def test_format_population_pipeline_summary_line_includes_class_count(monkeypatch) -> None:
    """Population summary helper should include class count and row accounting."""
    monkeypatch.setattr(app_config, "RUNTIME_TRAINING_LABEL_CLASS_COUNT", 13, raising=False)
    mc = {
        "cohort_prepared_row_count": 1226,
        "fused_feature_rows": 1226,
        "aligned_supervised_rows": 1220,
        "post_low_support_training_rows": 712,
        "train_sample_count": 534,
        "test_sample_count": 178,
    }
    line = format_population_pipeline_summary_line(mc)
    assert "governed_cohort_n=1226" in line
    assert "fused_feature_matrix_n=1226" in line
    assert "train_n=534" in line
    assert "test_n=178" in line
    assert "distinct_family_labels_after_support=13" in line


def test_format_population_pipeline_summary_line_empty_without_core_counts() -> None:
    """Empty payload should return an empty summary line."""
    assert format_population_pipeline_summary_line({}) == ""


def test_run_classifier_pipeline_drops_low_support_without_other_group(monkeypatch, tmp_path: Path) -> None:
    """Default low-support behavior should drop rows, not create a synthetic 'other' class."""
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_FEATURE_CONTRACT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_LEAKAGE_ASSESSMENT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "GROUP_LOW_SUPPORT_LABELS", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", 20, raising=False)

    captured: dict[str, object] = {}

    features = pd.DataFrame({"f1": [0.1, 0.2]}, index=[1, 2])
    labels = pd.Series(["fam_a", "fam_b"], index=[1, 2], name="family")

    monkeypatch.setattr(pipeline_core, "align_data", lambda *_args, **_kwargs: (features, labels))
    monkeypatch.setattr(
        pipeline_core.distribution_reporter,
        "print_family_distribution",
        lambda *_args, **_kwargs: None,
    )

    def _fake_apply_min_family_support(**kwargs):
        captured.update(kwargs)
        return kwargs["features_df"], kwargs["labels_df"], 0, 0, []

    monkeypatch.setattr(
        pipeline_core.distribution_reporter,
        "apply_min_family_support",
        _fake_apply_min_family_support,
    )
    monkeypatch.setattr(pipeline_core, "_prune_low_information_features", lambda df: df)
    monkeypatch.setattr(
        pipeline_core,
        "_prune_potential_leakage_features",
        lambda feature_df, _labels_df: feature_df,
    )
    monkeypatch.setattr(
        pipeline_core,
        "train_models",
        lambda *_args, **_kwargs: (
            {"logistic_regression": {"evaluation": {"accuracy": 1.0}}},
            [],
        ),
    )
    monkeypatch.setattr(pipeline_core, "summarize_models", lambda _results: "logistic_regression")
    monkeypatch.setattr(pipeline_core, "promote_default_model", lambda *_args, **_kwargs: None)

    result = pipeline_core.run_classifier_pipeline(
        features_df=features,
        samples_df=pd.DataFrame(
            {
                "sample_id": [1, 2],
                "type_slug": ["banker", "adware"],
                "family_canonical": ["fam_a", "fam_b"],
            }
        ),
        save_model=False,
        models=["logistic_regression"],
    )

    assert "logistic_regression" in result
    assert int(captured["min_support"]) == 20
    assert captured["group_label"] is None
    runtime_meta = getattr(app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", pd.DataFrame())
    assert "type_slug" in runtime_meta.columns
