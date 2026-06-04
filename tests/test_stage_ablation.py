"""Tests for ablation pipeline utility helpers."""

import contextlib
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from obsidiandroid.pipeline import stage_ablation
from obsidiandroid.pipeline.ablation import registry
from config import app_config
from obsidiandroid.modeling import model_trainer_factory


def test_resolve_vendor_include_fields_stays_full_under_evidence_controls(monkeypatch) -> None:
    """Ablation registry keeps the risky lexical surface available for leakage comparison."""

    monkeypatch.setattr(registry.app_config, "RUNTIME_EVIDENCE_STRICT_MODE", True, raising=False)
    monkeypatch.setattr(registry.app_config, "RUNTIME_EVIDENCE_MODE", False, raising=False)
    assert registry._resolve_vendor_include_fields() == [  # pylint: disable=protected-access
        "Parsed Family",
        "Threat Class",
        "Malware Type",
    ]

    monkeypatch.setattr(registry.app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(registry.app_config, "RUNTIME_EVIDENCE_MODE", True, raising=False)
    assert registry._resolve_vendor_include_fields() == [  # pylint: disable=protected-access
        "Parsed Family",
        "Threat Class",
        "Malware Type",
    ]

    monkeypatch.setattr(registry.app_config, "RUNTIME_EVIDENCE_MODE", False, raising=False)
    assert registry._resolve_vendor_include_fields() == [  # pylint: disable=protected-access
        "Parsed Family",
        "Threat Class",
        "Malware Type",
    ]


def test_build_experiment_matrix_dict_keeps_vendor_experiments_semantically_distinct_in_evidence_mode(
    monkeypatch,
) -> None:
    """vendor_full/full_fused should not collapse onto vendor_no_parsed_family in evidence mode."""
    monkeypatch.setattr(registry.app_config, "RUNTIME_EVIDENCE_STRICT_MODE", True, raising=False)
    monkeypatch.setattr(registry.app_config, "RUNTIME_EVIDENCE_MODE", True, raising=False)

    captured: list[tuple[list[str], bool]] = []

    def _fake_build_vendor_matrix(
        _weights_df,
        _parsed_data,
        include_fields,
        extra_features_df=None,
        cohort_sample_ids=None,
    ):
        del cohort_sample_ids
        captured.append((list(include_fields), extra_features_df is not None))
        return pd.DataFrame({"f1": [1.0]}, index=[1])

    monkeypatch.setattr(registry, "build_vendor_matrix", _fake_build_vendor_matrix)

    builders = registry.build_experiment_matrix_dict(
        weights_df=pd.DataFrame(),
        parsed_data={},
        permission_features_df=pd.DataFrame({"sample_id": [1], "perm_grp__sms_telephony_count": [1]}),
        pipeline_results=None,
        cohort_sample_ids=[1],
        permissions_band_builder=lambda _df, _subset: pd.DataFrame({"perm_grp__sms_telephony_count": [1]}, index=[1]),
    )

    builders["vendor_full"]()
    builders["vendor_no_parsed_family"]()
    builders["full_fused"]()

    assert captured[0] == (["Parsed Family", "Threat Class", "Malware Type"], False)
    assert captured[1] == (["Threat Class", "Malware Type"], False)
    assert captured[2] == (["Parsed Family", "Threat Class", "Malware Type"], True)


def test_load_paper_cohort_sample_ids_missing_column_returns_empty_set() -> None:
    """Missing sample_id column should not raise and should return empty set."""
    samples_df = pd.DataFrame({"sha256": ["a", "b"]})
    result = stage_ablation._load_paper_cohort_sample_ids(samples_df)  # pylint: disable=protected-access
    assert result == set()


def test_load_paper_cohort_sample_ids_from_runtime_dataframe() -> None:
    """sample_id values should be normalized to int set with invalid rows dropped."""
    samples_df = pd.DataFrame({"sample_id": [1, "2", None, "bad", 3]})
    result = stage_ablation._load_paper_cohort_sample_ids(samples_df)  # pylint: disable=protected-access
    assert result == {1, 2, 3}


def test_prepare_training_inputs_uses_runtime_min_support_and_no_other_by_default(
    monkeypatch,
) -> None:
    """Ablation prep should mirror pipeline support filtering without synthetic class by default."""
    features = pd.DataFrame({"f1": [0.1, 0.2]}, index=[1, 2])
    labels = pd.Series(["fam_a", "fam_b"], index=[1, 2], name="family")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        stage_ablation.pipeline_core,
        "align_data",
        lambda *_args, **_kwargs: (features, labels),
    )
    monkeypatch.setattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", 20, raising=False)
    monkeypatch.setattr(app_config, "GROUP_LOW_SUPPORT_LABELS", False, raising=False)

    def _fake_apply_min_family_support(**kwargs):
        captured.update(kwargs)
        return kwargs["features_df"], kwargs["labels_df"], 0, 0, []

    monkeypatch.setattr(
        stage_ablation.distribution_reporter,
        "apply_min_family_support",
        _fake_apply_min_family_support,
    )
    monkeypatch.setattr(stage_ablation.pipeline_core, "_prune_low_information_features", lambda df: df)
    monkeypatch.setattr(
        stage_ablation.pipeline_core,
        "_prune_potential_leakage_features",
        lambda feature_df, _labels_df: feature_df,
    )

    out_features, out_labels = stage_ablation._prepare_training_inputs(  # pylint: disable=protected-access
        feature_df=features,
        samples_df=pd.DataFrame({"sample_id": [1, 2]}),
    )

    assert out_features is not None
    assert out_labels is not None
    assert int(captured["min_support"]) == 20
    assert captured["group_label"] is None


def test_reindex_ablation_features_to_frozen_ids_zero_fills_missing_rows() -> None:
    """Missing vendor rows become explicit zeros on the frozen cohort index."""
    frozen = [1, 2, 3]
    raw = pd.DataFrame({"f": [0.5, 0.25]}, index=[1, 3])
    out = stage_ablation.reindex_ablation_features_to_frozen_ids(raw, frozen)
    assert list(out.index) == frozen
    assert float(out.loc[2, "f"]) == 0.0
    assert float(out.loc[1, "f"]) == 0.5


def test_reindex_ablation_features_with_sample_id_column() -> None:
    raw = pd.DataFrame({"sample_id": [2, 1], "x": [10.0, 20.0]})
    out = stage_ablation.reindex_ablation_features_to_frozen_ids(raw, [1, 2, 3])
    assert list(out.index) == [1, 2, 3]
    assert float(out.loc[3, "x"]) == 0.0


def test_split_cache_key_ignores_feature_count_during_ablation(monkeypatch) -> None:
    """Ablations differ in column count; train/test split must still reuse the same cache key."""
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    idx = pd.Index([10, 20, 30, 40])
    y = np.array([0, 1, 0, 1])
    small = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]}, index=idx)
    large = pd.DataFrame(
        {f"c{i}": [float(j) for j in range(4)] for i in range(5)},
        index=idx,
    )
    k1 = model_trainer_factory._build_split_cache_key(small, y, 0.25, 42, group_aware_requested=False)
    k2 = model_trainer_factory._build_split_cache_key(large, y, 0.25, 42, group_aware_requested=False)
    assert k1 == k2


def test_split_cache_key_varies_with_feature_count_when_not_ablation(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", False, raising=False)
    idx = pd.Index([10, 20, 30, 40])
    y = np.array([0, 1, 0, 1])
    small = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]}, index=idx)
    large = pd.DataFrame(
        {f"c{i}": [float(j) for j in range(4)] for i in range(5)},
        index=idx,
    )
    k1 = model_trainer_factory._build_split_cache_key(small, y, 0.25, 42, group_aware_requested=False)
    k2 = model_trainer_factory._build_split_cache_key(large, y, 0.25, 42, group_aware_requested=False)
    assert k1 != k2


def test_ablation_split_cache_reslices_current_feature_columns(monkeypatch) -> None:
    """Second feature matrix must train with its own columns when split cache hits."""
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "ut_ablation_cols", raising=False)
    monkeypatch.setattr(app_config, "TRAIN_TEST_SPLIT", 0.33)
    monkeypatch.setattr(app_config, "RANDOM_STATE", 0)
    monkeypatch.setattr(app_config, "ENABLE_SMOTE_OVERSAMPLING", False)
    monkeypatch.setattr(model_trainer_factory, "_export_split_audit", lambda **_kw: None)
    model_trainer_factory.reset_runtime_training_caches()

    captured: list[list[str]] = []

    def _fake_trainer(**kwargs):
        captured.append(list(kwargs["X_train"].columns))
        fit_cols = list(kwargs["X_train"].columns)

        class _Dummy:
            feature_names_in_ = np.array(fit_cols)

            def predict(self, X):
                return np.zeros(len(X))

            def predict_proba(self, X):
                return np.ones((len(X), 2)) * 0.5

        return _Dummy(), {}

    monkeypatch.setattr(model_trainer_factory, "get_model_trainer", lambda _mt: _fake_trainer)

    idx = list(range(30))
    labels = pd.Series((["a", "b", "c"] * 10)[:30], index=idx)
    df_vendor = pd.DataFrame({f"v{i}": np.arange(30) + i for i in range(2)}, index=idx)
    df_perm = pd.DataFrame({f"p{i}": np.arange(30) * i for i in range(3)}, index=idx)

    model_trainer_factory.train_model_factory(
        features_df=df_vendor,
        labels=labels,
        model_type="logistic_regression",
    )
    model_trainer_factory.train_model_factory(
        features_df=df_perm,
        labels=labels,
        model_type="logistic_regression",
    )

    assert len(captured) == 2
    assert all(c.startswith("v") for c in captured[0])
    assert all(c.startswith("p") for c in captured[1])


def test_schema_audit_ok_when_names_match(monkeypatch) -> None:
    """Schema audit should pass when feature names are unchanged."""
    monkeypatch.setattr(app_config, "RUNTIME_EXPERIMENT_ID", "vendor_only", raising=False)
    X = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    m = LogisticRegression()
    m.fit(X, [0, 1])
    from obsidiandroid.features import feature_schema_audit

    row = feature_schema_audit.build_ablation_schema_audit_row(
        model=m, model_type="logistic_regression", features_df=X
    )
    assert row["status"] == "OK"
    assert row["missing_at_predict_count"] == 0
    assert row["extra_at_predict_count"] == 0


def test_schema_audit_detects_extra_columns(monkeypatch) -> None:
    """Schema audit should report extras when prediction features differ."""
    monkeypatch.setattr(app_config, "RUNTIME_EXPERIMENT_ID", "permissions_only", raising=False)
    fit_df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    m = LogisticRegression()
    m.fit(fit_df, [0, 1])
    pred_df = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [0, 0]})
    from obsidiandroid.features import feature_schema_audit

    row = feature_schema_audit.build_ablation_schema_audit_row(
        model=m, model_type="logistic_regression", features_df=pred_df
    )
    assert row["status"] == "schema_mismatch"
    assert row["extra_at_predict_count"] == 1


def test_print_ablation_terminal_summary_compact_mode_reduces_grid(monkeypatch) -> None:
    captured_tables: list[pd.DataFrame] = []
    captured_info: list[str] = []

    monkeypatch.setattr(app_config, "ML_TERMINAL_COMPACT", True, raising=False)
    monkeypatch.setattr(stage_ablation.ml_console, "is_minimal", lambda: False)
    monkeypatch.setattr(stage_ablation.du, "print_section", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        stage_ablation.du,
        "print_table",
        lambda df, **_kwargs: captured_tables.append(df.copy()),
    )
    monkeypatch.setattr(stage_ablation.du, "print_info", lambda msg, *_args, **_kwargs: captured_info.append(str(msg)))

    summary_df = pd.DataFrame(
        [
            {"label_target": "family_id", "experiment": "full_fused", "model": "xgboost", "macro_f1_score": 0.98, "delta_vs_full_fused": 0.0},
            {"label_target": "family_id", "experiment": "permissions_grouped", "model": "random_forest", "macro_f1_score": 0.93, "delta_vs_full_fused": -0.05},
            {"label_target": "family_id", "experiment": "vendor_no_parsed_family", "model": "random_forest", "macro_f1_score": 0.81, "delta_vs_full_fused": -0.17},
            {"label_target": "family_id", "experiment": "vendor_full", "model": "random_forest", "macro_f1_score": 0.91, "delta_vs_full_fused": -0.07},
            {"label_target": "type_slug", "experiment": "full_fused", "model": "xgboost", "macro_f1_score": 0.99, "delta_vs_full_fused": 0.0},
            {"label_target": "type_slug", "experiment": "vendor_full", "model": "random_forest", "macro_f1_score": 0.97, "delta_vs_full_fused": -0.02},
            {"label_target": "type_slug", "experiment": "permissions_raw", "model": "random_forest", "macro_f1_score": 0.95, "delta_vs_full_fused": -0.04},
            {"label_target": "type_slug", "experiment": "vendor_no_parsed_family", "model": "random_forest", "macro_f1_score": 0.88, "delta_vs_full_fused": -0.11},
            {"label_target": "family_within_type", "experiment": "full_fused", "model": "xgboost", "macro_f1_score": 0.73, "delta_vs_full_fused": 0.0},
        ]
    )

    stage_ablation._print_ablation_terminal_summary(summary_df)  # pylint: disable=protected-access

    assert len(captured_tables) == 1
    compact_df = captured_tables[0]
    assert list(compact_df.columns) == [
        "label_target",
        "best_feature_set",
        "best_model",
        "best_macro_f1",
        "permission_only",
        "vendor_safe",
        "full_fused",
        "delta_permission_vs_full_fused",
        "parsed_family_gap",
    ]
    assert len(compact_df) == 3
    assert compact_df["best_feature_set"].tolist() == ["full_fused", "full_fused", "full_fused"]
    assert any("Permissions carry strong independent family/type signal" in msg for msg in captured_info)
    assert any("Parsed vendor family strings are leakage-sensitive" in msg for msg in captured_info)
    assert any("type_slug is easier than family_id" in msg for msg in captured_info)
    assert any("family_within_type remains harder" in msg for msg in captured_info)
    assert any("Full experiment grid remains in diagnostics CSV/Markdown summaries." in msg for msg in captured_info)


def test_print_ablation_combo_summary_compacts_model_timings(monkeypatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(stage_ablation.du, "print_info", lambda msg, *_a, **_k: captured.append(str(msg)))
    monkeypatch.setattr(stage_ablation.ml_console, "is_debug", lambda: True)

    stage_ablation._print_ablation_combo_summary(  # pylint: disable=protected-access
        "full_fused",
        "family_canonical_default",
        {
            "random_forest": {"evaluation": {"macro_f1_score": 0.91, "train_time": 2.5}},
            "xgboost": {"evaluation": {"macro_f1_score": 0.94, "train_time": 9.75}},
            "logistic_regression": {"evaluation": {"macro_f1_score": 0.88, "train_time": 1.25}},
        },
    )

    assert len(captured) == 1
    assert "[ABLATION] full_fused / family_canonical_default: 3 model(s)" in captured[0]
    assert "best=xgboost MacroF1=0.9400" in captured[0]
    assert "fit_total=13.50s" in captured[0]
    assert "slowest=xgboost 9.75s" in captured[0]


def test_print_ablation_cohort_integrity_table_compacts_all_ok_rows(monkeypatch) -> None:
    captured_info: list[str] = []
    captured_tables: list[pd.DataFrame] = []
    monkeypatch.setattr(stage_ablation.ml_console, "is_minimal", lambda: False)
    monkeypatch.setattr(stage_ablation.ml_console, "is_debug", lambda: False)
    monkeypatch.setattr(stage_ablation.du, "print_info", lambda msg, *_a, **_k: captured_info.append(str(msg)))
    monkeypatch.setattr(stage_ablation.du, "print_table", lambda df, **_kwargs: captured_tables.append(df.copy()))

    stage_ablation._print_ablation_cohort_integrity_table(  # pylint: disable=protected-access
        [
            {
                "feature_set": "full_fused",
                "expected_ids": 1247,
                "raw_matrix_ids": 1247,
                "missing_vs_expected": 0,
                "final_aligned_ids": 1247,
                "status": "OK",
            },
            {
                "feature_set": "permissions_grouped",
                "expected_ids": 1247,
                "raw_matrix_ids": 1247,
                "missing_vs_expected": 0,
                "final_aligned_ids": 1247,
                "status": "OK",
            },
        ]
    )

    assert captured_tables == []
    assert captured_info == [
        "[ABLATION] Cohort integrity: PASS — 2/2 feature sets aligned to 1,247 sample_ids; missing IDs=0."
    ]


def test_build_ablation_feature_set_summary_rows_uses_terminal_labels() -> None:
    built = pd.DataFrame({"f1": [1.0], "f2": [2.0]}, index=[1])
    built.attrs["selected_vendors"] = ["vendor_a", "vendor_b"]
    built.attrs["feature_effective_top_k"] = 2

    rows = stage_ablation._build_ablation_feature_set_summary_rows(  # pylint: disable=protected-access
        experiment_order=["vendor_full", "permissions_grouped", "vendor_no_family_no_type"],
        built_matrices={"vendor_full": built, "permissions_grouped": pd.DataFrame({"p": [1.0]}, index=[1])},
        skipped_experiments=[
            {
                "feature_set": "vendor_no_family_no_type",
                "reason": "empty_feature_matrix",
                "detail": "Builder returned a non-DataFrame or empty feature matrix.",
            }
        ],
    )

    assert rows[0]["feature_set"] == "vendor_parsed_full"
    assert rows[0]["selected_vendors"] == "2"
    assert rows[0]["effective_top_k"] == "2"
    assert rows[1]["feature_set"] == "permissions_grouped"
    assert rows[1]["selected_vendors"] == "—"
    assert rows[2]["feature_set"] == "vendor_without_family_or_type_strings"
    assert rows[2]["status"] == "SKIPPED"


def test_apply_leakage_delta_prefers_vendor_no_parsed_family_baseline() -> None:
    summary_df = pd.DataFrame(
        [
            {
                "label_target": "family_id",
                "experiment": "vendor_full",
                "model": "random_forest",
                "macro_f1_score": 0.90,
            },
            {
                "label_target": "family_id",
                "experiment": "vendor_no_parsed_family",
                "model": "random_forest",
                "macro_f1_score": 0.70,
            },
            {
                "label_target": "family_id",
                "experiment": "full_fused",
                "model": "random_forest",
                "macro_f1_score": 0.95,
            },
        ]
    )

    out = stage_ablation._apply_leakage_delta(summary_df)  # pylint: disable=protected-access
    full_fused = out[out["experiment"] == "full_fused"].iloc[0]
    vendor_full = out[out["experiment"] == "vendor_full"].iloc[0]

    assert float(full_fused["vendor_leakage_delta_vs_vendor_safe"]) == 0.25
    assert float(full_fused["vendor_leakage_delta_vs_vendor_full"]) == 0.25
    assert float(vendor_full["vendor_leakage_delta_vs_vendor_safe"]) == 0.20


def test_run_ablation_experiments_persists_skipped_feature_sets(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(stage_ablation, "_diagnostics_dir", lambda: tmp_path)
    monkeypatch.setattr(
        stage_ablation,
        "_load_paper_cohort_sample_ids",
        lambda _samples_df: {1, 2},
    )
    monkeypatch.setattr(
        stage_ablation,
        "_build_experiment_matrix_dict",
        lambda *_args, **_kwargs: {
            "vendor_full": lambda: pd.DataFrame({"f1": [0.1, 0.2]}, index=[1, 2]),
            "vendor_no_family_no_type": lambda: pd.DataFrame(),
        },
    )
    monkeypatch.setattr(
        stage_ablation,
        "_prepare_training_inputs",
        lambda feature_df, _samples_df, forced_label_column=None: (
            feature_df,
            pd.Series(
                ["fam_a", "fam_b"],
                index=feature_df.index,
                name=forced_label_column or "family_canonical",
            ),
        ),
    )
    monkeypatch.setattr(stage_ablation, "_print_ablation_cohort_integrity_table", lambda *_a, **_k: None)
    monkeypatch.setattr(stage_ablation, "_print_ablation_terminal_summary", lambda *_a, **_k: None)
    monkeypatch.setattr(
        stage_ablation.pipeline_core,
        "train_models",
        lambda *_args, **_kwargs: (
            {
                "random_forest": {
                    "evaluation": {
                        "accuracy": 0.9,
                        "f1_score": 0.88,
                        "macro_f1_score": 0.77,
                        "macro_precision": 0.75,
                        "macro_recall": 0.76,
                        "samples_tested": 2,
                    },
                    "metadata": {},
                }
            },
            None,
        ),
    )
    monkeypatch.setattr(app_config, "ENABLE_ABLATION_MULTI_LABEL_TARGETS", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ABLATION_CROSS_VALIDATION", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ABLATION_MODEL_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ABLATION_COHORT_REINDEX_ZERO_FILL", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_LEDGER_INDEX", {}, raising=False)

    manifest_context: dict[str, object] = {}
    artifact_paths = stage_ablation.run_ablation_experiments(
        samples_df=pd.DataFrame({"sample_id": [1, 2], "family_canonical": ["fam_a", "fam_b"]}),
        weights_df=pd.DataFrame(),
        parsed_data={},
        permission_features_df=None,
        model_list=["random_forest"],
        run_id="rid",
        pipeline_results={},
        manifest_context=manifest_context,
    )

    assert any("ablation_run_outcome_rid.json" in path for path in artifact_paths)
    outcome = json.loads((tmp_path / "ablation_run_outcome_rid.json").read_text(encoding="utf-8"))
    expected_skip = [
        {
            "feature_set": "vendor_no_family_no_type",
            "reason": "empty_feature_matrix",
            "detail": "Builder returned a non-DataFrame or empty feature matrix.",
        }
    ]
    assert outcome["ablation_grid_status"] == "complete"
    assert outcome["trainable_experiments"] == 1
    assert outcome["skipped_experiment_count"] == 1
    assert outcome["skipped_experiments"] == expected_skip
    assert manifest_context["_ablation_skipped_experiments"] == expected_skip
    assert manifest_context["_ablation_cohort_gap_summary"]["skipped_experiments"] == expected_skip


def test_run_ablation_experiments_prefers_family_id_as_primary_family_target(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(stage_ablation, "_diagnostics_dir", lambda: tmp_path)
    monkeypatch.setattr(stage_ablation, "_load_paper_cohort_sample_ids", lambda _samples_df: {1, 2})
    monkeypatch.setattr(
        stage_ablation,
        "_build_experiment_matrix_dict",
        lambda *args, **_kwargs: {
            "full_fused": lambda: pd.DataFrame({"sample_id": [1, 2], "f1": [1.0, 0.0]})
        },
    )
    monkeypatch.setattr(
        stage_ablation.pipeline_core,
        "train_models",
        lambda *args, **kwargs: (
            {
                "random_forest": {
                    "evaluation": {"macro_f1_score": 0.9, "train_time": 1.0},
                    "metadata": {},
                }
            },
            None,
        ),
    )
    monkeypatch.setattr(app_config, "ENABLE_ABLATION_MULTI_LABEL_TARGETS", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ABLATION_CROSS_VALIDATION", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ABLATION_MODEL_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ABLATION_COHORT_REINDEX_ZERO_FILL", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid2", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_LEDGER_INDEX", {}, raising=False)

    manifest_context: dict[str, object] = {}
    stage_ablation.run_ablation_experiments(
        samples_df=pd.DataFrame(
            {
                "sample_id": [1, 2],
                "family_id": [10, 11],
                "family_canonical": ["fam_a", "fam_b"],
                "type_slug": ["banker", "rat"],
            }
        ),
        weights_df=pd.DataFrame(),
        parsed_data={},
        permission_features_df=None,
        model_list=["random_forest"],
        run_id="rid2",
        pipeline_results={},
        manifest_context=manifest_context,
    )

    stats = manifest_context.get("_ablation_label_target_stats")
    assert isinstance(stats, list)
    assert str(stats[0]["label_target"]) == "family_id"


def test_run_ablation_experiments_wraps_grid_in_sklearn_warning_suppression(
    tmp_path, monkeypatch
) -> None:
    entered: list[str] = []

    @contextlib.contextmanager
    def _fake_warning_suppression():
        entered.append("enter")
        try:
            yield
        finally:
            entered.append("exit")

    monkeypatch.setattr(stage_ablation, "_diagnostics_dir", lambda: tmp_path)
    monkeypatch.setattr(stage_ablation, "_load_paper_cohort_sample_ids", lambda _samples_df: {1, 2})
    monkeypatch.setattr(
        stage_ablation,
        "_build_experiment_matrix_dict",
        lambda *args, **kwargs: {
            "full_fused": lambda: pd.DataFrame({"sample_id": [1, 2], "f1": [1.0, 0.0]})
        },
    )
    monkeypatch.setattr(
        stage_ablation.pipeline_core,
        "train_models",
        lambda *args, **kwargs: (
            {
                "random_forest": {
                    "evaluation": {"macro_f1_score": 0.9, "train_time": 1.0},
                    "metadata": {},
                }
            },
            None,
        ),
    )
    monkeypatch.setattr(
        stage_ablation.pipeline_core,
        "_suppress_known_sklearn_parallel_warning",
        _fake_warning_suppression,
    )
    monkeypatch.setattr(app_config, "ENABLE_ABLATION_MULTI_LABEL_TARGETS", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ABLATION_CROSS_VALIDATION", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_ABLATION_MODEL_EXPORT", False, raising=False)
    monkeypatch.setattr(app_config, "ABLATION_COHORT_REINDEX_ZERO_FILL", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid3", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_SPLIT_LEDGER_INDEX", {}, raising=False)

    stage_ablation.run_ablation_experiments(
        samples_df=pd.DataFrame(
            {
                "sample_id": [1, 2],
                "family_canonical": ["fam_a", "fam_b"],
            }
        ),
        weights_df=pd.DataFrame(),
        parsed_data={},
        permission_features_df=None,
        model_list=["random_forest"],
        run_id="rid3",
        pipeline_results={},
        manifest_context={},
    )

    assert entered == ["enter", "exit"]
