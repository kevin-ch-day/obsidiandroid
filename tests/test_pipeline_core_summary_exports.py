"""Tests for model-summary export behavior in pipeline_core."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.orchestration.runtime_reporting import format_population_pipeline_summary_line
from obsidiandroid.orchestration import runtime_reporting
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
        lambda _results, **_kwargs: pd.DataFrame(
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
        lambda _results, **_kwargs: pd.DataFrame(
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


def test_summarize_models_exports_family_tier_evaluation_for_family_target(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Family-target runs should export major/minor tier-aware held-out metrics."""
    run_id = "20260601T000000Z__familytiers"
    output_root = tmp_path / "output"
    diagnostics_dir = output_root / "runs" / run_id / "diagnostics"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_MODEL_COMPARISON_CSV_EXPORT", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_MODEL_COMPARISON_EXCEL_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_RF_IMPURITY_IMPORTANCE_EXPORT", False, raising=False)
    monkeypatch.setattr(
        app_config,
        "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD",
        "family_id",
        raising=False,
    )
    monkeypatch.setattr(
        app_config,
        "RUNTIME_SPLIT_SAMPLE_METADATA",
        pd.DataFrame(
            {
                "sample_id": [101, 102, 103],
                "family_id": [11, 22, None],
                "family_canonical": ["SpyNote", "Gigabud", None],
                "type_slug": ["rat", "rat", "banker"],
                "category_primary": ["malware", "malware", ""],
                "category_subtype": ["rat", "rat", ""],
                "sample_label_kind": ["family_or_common_name", "family_or_common_name", ""],
            }
        ),
        raising=False,
    )
    monkeypatch.setattr(
        pipeline_core.comparator,
        "compare_model_performance",
        lambda _results, **_kwargs: pd.DataFrame([{"Model": "random_forest", "Macro F1-Score": 0.80}]),
    )
    monkeypatch.setattr(
        pipeline_core.inspector,
        "generate_classification_summary",
        lambda **_kwargs: None,
    )

    results = {
        "random_forest": {
            "evaluation": {
                "accuracy": 0.75,
                "macro_f1_score": 0.80,
                "confusion_matrix_path": "cm.png",
                "y_true": ["spynote", "gigabud", "banker"],
                "y_pred": ["spynote", "spynote", "banker"],
            },
            "X_test": pd.DataFrame(index=[101, 102, 103]),
        }
    }

    top_model = pipeline_core.summarize_models(results)

    assert top_model == "random_forest"
    tier_csv = diagnostics_dir / f"family_tier_model_evaluation_{run_id}.csv"
    assert tier_csv.exists()
    tier_df = pd.read_csv(tier_csv)
    assert set(tier_df["evaluation_scope"].tolist()) == {
        "overall",
        "major",
        "minor",
        "generic_or_coarse",
        "unresolved",
    }
    major_row = tier_df[tier_df["evaluation_scope"] == "major"].iloc[0]
    minor_row = tier_df[tier_df["evaluation_scope"] == "minor"].iloc[0]
    unresolved_row = tier_df[tier_df["evaluation_scope"] == "unresolved"].iloc[0]
    assert int(major_row["sample_count"]) == 1
    assert int(minor_row["sample_count"]) == 1
    assert int(unresolved_row["sample_count"]) == 1


def test_summarize_models_skips_family_tier_evaluation_for_type_target(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Type-target runs should not emit family-tier held-out evaluation exports."""
    run_id = "20260601T000000Z__typetiers"
    output_root = tmp_path / "output"
    diagnostics_dir = output_root / "runs" / run_id / "diagnostics"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_MODEL_COMPARISON_CSV_EXPORT", True, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_MODEL_COMPARISON_EXCEL_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_RF_IMPURITY_IMPORTANCE_EXPORT", False, raising=False)
    monkeypatch.setattr(
        app_config,
        "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD",
        "type_slug",
        raising=False,
    )
    monkeypatch.setattr(
        app_config,
        "RUNTIME_SPLIT_SAMPLE_METADATA",
        pd.DataFrame({"sample_id": [101], "type_slug": ["banker"]}),
        raising=False,
    )
    monkeypatch.setattr(
        pipeline_core.comparator,
        "compare_model_performance",
        lambda _results, **_kwargs: pd.DataFrame([{"Model": "logistic_regression", "Macro F1-Score": 0.70}]),
    )
    monkeypatch.setattr(
        pipeline_core.inspector,
        "generate_classification_summary",
        lambda **_kwargs: None,
    )

    results = {
        "logistic_regression": {
            "evaluation": {
                "accuracy": 0.70,
                "macro_f1_score": 0.70,
                "confusion_matrix_path": "cm.png",
                "y_true": ["banker"],
                "y_pred": ["banker"],
            },
            "X_test": pd.DataFrame(index=[101]),
        }
    }

    top_model = pipeline_core.summarize_models(results)

    assert top_model == "logistic_regression"
    tier_csv = diagnostics_dir / f"family_tier_model_evaluation_{run_id}.csv"
    assert not tier_csv.exists()


def test_extract_model_summary_includes_top_model_family_tier_rows(monkeypatch) -> None:
    """Run-summary payload should carry family-tier rows for the promoted top model."""
    monkeypatch.setattr(
        app_config,
        "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD",
        "family_id",
        raising=False,
    )
    monkeypatch.setattr(
        app_config,
        "RUNTIME_SPLIT_SAMPLE_METADATA",
        pd.DataFrame(
            {
                "sample_id": [201, 202],
                "family_id": [11, 22],
                "family_canonical": ["SpyNote", "Gigabud"],
                "type_slug": ["rat", "rat"],
                "category_primary": ["malware", "malware"],
                "category_subtype": ["rat", "rat"],
                "sample_label_kind": ["family_or_common_name", "family_or_common_name"],
            }
        ),
        raising=False,
    )

    summary = runtime_reporting.extract_model_summary(
        {
            "random_forest": {
                "evaluation": {
                    "accuracy": 0.8,
                    "macro_f1_score": 0.8,
                    "f1_score": 0.81,
                    "y_true": ["spynote", "gigabud"],
                    "y_pred": ["spynote", "spynote"],
                },
                "X_test": pd.DataFrame(index=[201, 202]),
            },
            "logistic_regression": {
                "evaluation": {
                    "accuracy": 0.7,
                    "macro_f1_score": 0.7,
                    "f1_score": 0.7,
                    "y_true": ["spynote", "gigabud"],
                    "y_pred": ["spynote", "gigabud"],
                },
                "X_test": pd.DataFrame(index=[201, 202]),
            },
        }
    )

    assert summary["top_model"] == "random_forest"
    assert summary["top_model_primary_metric_name"] == "macro_f1_score"
    assert summary["top_model_primary_metric_value"] == 0.8
    assert summary["top_model_primary_metric_tier"] == "T4 - Above Average (80-84%)"
    assert summary["top_model_weighted_f1_tier"] == "T4 - Above Average (80-84%)"
    assert summary["top_model_accuracy_tier"] == "T4 - Above Average (80-84%)"
    assert isinstance(summary.get("family_tier_model_rows"), list)
    top_rows = summary.get("top_model_family_tier_rows", [])
    assert {row["evaluation_scope"] for row in top_rows} == {
        "overall",
        "major",
        "minor",
        "generic_or_coarse",
        "unresolved",
    }
    assert all(row["model"] == "random_forest" for row in top_rows)


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


def test_format_population_pipeline_summary_line_uses_modeled_class_wording_for_diagnostic_only(
    monkeypatch,
) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_TRAINING_LABEL_CLASS_COUNT", 115, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SUPPORT_FLOOR_MODE", "diagnostic_only", raising=False)
    mc = {
        "cohort_prepared_row_count": 3644,
        "fused_feature_rows": 3644,
        "aligned_supervised_rows": 3433,
        "post_low_support_training_rows": 3433,
        "train_sample_count": 2574,
        "test_sample_count": 859,
    }
    line = format_population_pipeline_summary_line(mc)
    assert "actual_modeled_family_classes=115" in line
    assert "distinct_family_labels_after_support" not in line


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


def test_run_classifier_pipeline_keeps_low_support_when_support_floor_is_diagnostic_only(
    monkeypatch, tmp_path: Path
) -> None:
    """Diagnostic-only support mode should not drop low-support families before training."""
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_FEATURE_CONTRACT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_LEAKAGE_ASSESSMENT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "GROUP_LOW_SUPPORT_LABELS", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", 3, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SUPPORT_FLOOR_MODE", "diagnostic_only", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_QUIET_TRAINING", False, raising=False)

    captured: dict[str, object] = {}
    warnings: list[str] = []

    features = pd.DataFrame({"f1": [0.1, 0.2]}, index=[1, 2])
    labels = pd.Series(["fam_a", "fam_b"], index=[1, 2], name="family")

    monkeypatch.setattr(pipeline_core, "align_data", lambda *_args, **_kwargs: (features, labels))
    monkeypatch.setattr(
        pipeline_core.distribution_reporter,
        "print_family_distribution",
        lambda *_args, **_kwargs: None,
    )

    def _should_not_run(**kwargs):
        captured.update(kwargs)
        raise AssertionError("apply_min_family_support should be skipped for diagnostic-only support mode")

    monkeypatch.setattr(
        pipeline_core.distribution_reporter,
        "apply_min_family_support",
        _should_not_run,
    )
    monkeypatch.setattr(
        pipeline_core.du,
        "print_warning",
        lambda message: warnings.append(str(message)),
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
    assert captured == {}
    assert not any("Family support filtering failed" in message for message in warnings)


def test_run_classifier_pipeline_applies_benchmark_eligibility_support_floor_for_family_targets(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_FEATURE_CONTRACT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_LEAKAGE_ASSESSMENT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "GROUP_LOW_SUPPORT_LABELS", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", 3, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SUPPORT_FLOOR_MODE", "benchmark_eligibility", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_QUIET_TRAINING", False, raising=False)

    captured: dict[str, object] = {}

    features = pd.DataFrame({"f1": [0.1, 0.2, 0.3]}, index=[1, 2, 3])
    labels = pd.Series(["fam_a", "fam_a", "fam_b"], index=[1, 2, 3], name="family_id")

    monkeypatch.setattr(pipeline_core, "align_data", lambda *_args, **_kwargs: (features, labels))
    monkeypatch.setattr(
        pipeline_core.distribution_reporter,
        "print_family_distribution",
        lambda *_args, **_kwargs: None,
    )

    def _fake_apply_min_family_support(**kwargs):
        captured.update(kwargs)
        return kwargs["features_df"], kwargs["labels_df"], 1, 1, [{"family": "fam_b", "aligned_support": 1}]

    monkeypatch.setattr(
        pipeline_core.distribution_reporter,
        "apply_min_family_support",
        _fake_apply_min_family_support,
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
                "sample_id": [1, 2, 3],
                "type_slug": ["banker", "banker", "rat"],
                "family_canonical": ["fam_a", "fam_a", "fam_b"],
            }
        ),
        save_model=False,
        models=["logistic_regression"],
    )

    assert "logistic_regression" in result
    assert int(captured["min_support"]) == 3
    assert app_config.RUNTIME_BENCHMARK_SUPPORT_APPLIED is True
    assert app_config.RUNTIME_BENCHMARK_SUPPORT_EXCLUDED_SAMPLE_COUNT == 1
    assert app_config.RUNTIME_BENCHMARK_SUPPORT_EXCLUDED_FAMILY_COUNT == 1
    assert app_config.RUNTIME_LOW_SUPPORT_FAMILY_DROP_DETAIL == [
        {"family": "fam_b", "aligned_support": 1}
    ]


def test_run_classifier_pipeline_skips_benchmark_eligibility_support_floor_for_type_targets(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "ENABLE_FEATURE_CONTRACT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_LEAKAGE_ASSESSMENT_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "GROUP_LOW_SUPPORT_LABELS", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", 3, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SUPPORT_FLOOR_MODE", "benchmark_eligibility", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_QUIET_TRAINING", False, raising=False)

    captured: dict[str, object] = {}

    features = pd.DataFrame({"f1": [0.1, 0.2]}, index=[1, 2])
    labels = pd.Series(["banker", "rat"], index=[1, 2], name="type_slug")

    monkeypatch.setattr(pipeline_core, "align_data", lambda *_args, **_kwargs: (features, labels))
    monkeypatch.setattr(
        pipeline_core.distribution_reporter,
        "print_family_distribution",
        lambda *_args, **_kwargs: None,
    )

    def _should_not_run(**kwargs):
        captured.update(kwargs)
        raise AssertionError("apply_min_family_support should be skipped for type-level targets")

    monkeypatch.setattr(
        pipeline_core.distribution_reporter,
        "apply_min_family_support",
        _should_not_run,
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
                "type_slug": ["banker", "rat"],
                "family_canonical": ["fam_a", "fam_b"],
            }
        ),
        save_model=False,
        models=["logistic_regression"],
    )

    assert "logistic_regression" in result
    assert captured == {}
    assert app_config.RUNTIME_BENCHMARK_SUPPORT_APPLIED is False
