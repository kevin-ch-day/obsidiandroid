"""Tests for AV/vendor stage helper utilities."""

import pandas as pd
import pytest

from obsidiandroid.diagnostics.av_selection_contract import export_av_selection_contract
from obsidiandroid.pipeline import av_engine_pipeline
from obsidiandroid.pipeline import stage_av_vendor
from config import app_config


def test_assert_engine_lifecycle_integrity_rejects_zero_included() -> None:
    """Lifecycle integrity should fail when no engines are included."""
    lifecycle_df = pd.DataFrame({"included_in_model_flag": [False, False]})

    with pytest.raises(ValueError, match="included_engines"):
        stage_av_vendor._assert_engine_lifecycle_integrity(lifecycle_df)  # pylint: disable=protected-access


def test_run_feature_alignment_stage_requires_label_columns() -> None:
    """Alignment stage should enforce required supervised label columns."""
    feature_df = pd.DataFrame({"sample_id": [1], "f1": [0.1]})
    samples_df = pd.DataFrame({"sample_id": [1], "family_canonical": ["x"]})

    with pytest.raises(ValueError, match="Missing required supervised label columns"):
        stage_av_vendor.run_feature_alignment_stage(
            feature_df=feature_df,
            samples_df=samples_df,
            diagnostics_dir="output/diagnostics",
        )


def test_assert_engine_count_consistency_rejects_mismatch() -> None:
    """Lifecycle/attrs mismatch should raise integrity error."""
    lifecycle_df = pd.DataFrame({"included_in_model_flag": [True, False, False]})
    scores_df = pd.DataFrame({"engine_name": ["a", "b", "c"]})
    scores_df.attrs["engine_included_count"] = 1
    scores_df.attrs["engine_excluded_count"] = 1

    with pytest.raises(ValueError, match="lifecycle/attrs mismatch"):
        stage_av_vendor._assert_engine_count_consistency(  # pylint: disable=protected-access
            lifecycle_df=lifecycle_df,
            engine_scores_df=scores_df,
        )


def test_run_av_analysis_stage_sets_runtime_engine_counts(monkeypatch) -> None:
    """AV stage should propagate included/excluded lifecycle counts to runtime config."""
    monkeypatch.setattr(app_config, "AV_BINARY_FEATURE_ENGINE_SCOPE", "lifecycle_included", raising=False)
    lifecycle_df = pd.DataFrame(
        {
            "included_in_model_flag": [True, False, True],
            "observed_flag": [True, True, True],
            "canonicalized_flag": [True, True, True],
        }
    )
    scores_df = pd.DataFrame({"engine_name": ["a", "b", "c"]})
    scores_df.attrs["engine_included_count"] = 2
    scores_df.attrs["engine_excluded_count"] = 1
    scores_df.attrs["engine_observed_count"] = 3
    scores_df.attrs["engine_canonical_count"] = 3
    scores_df.attrs["engine_near_miss_count"] = 1
    scores_df.attrs["engine_exclusion_audit_path"] = "obsidiandroid/output/runs/run123/diagnostics/engine_exclusion_audit_run123.csv"

    seen: dict[str, object] = {}

    def fake_av_pipeline(*_args, **kwargs):
        seen["config"] = kwargs.get("config")
        return {"engine_scores": scores_df, "engine_lifecycle": lifecycle_df}

    monkeypatch.setattr(stage_av_vendor.av_engine_pipeline, "run_av_analysis_pipeline", fake_av_pipeline)

    artifact_list: list[str] = []
    out = stage_av_vendor.run_av_analysis_stage(
        samples_df=pd.DataFrame({"sample_id": [1]}),
        run_id="run123",
        profile_id="dev_smoke",
        artifact_list=artifact_list,
    )

    assert out is not None
    assert int(getattr(app_config, "RUNTIME_ENGINE_COUNT_INCLUDED_AFTER_GATING", -1)) == 2
    assert int(getattr(app_config, "RUNTIME_ENGINE_COUNT_EXCLUDED_AFTER_GATING", -1)) == 1
    assert int(getattr(app_config, "RUNTIME_ENGINE_COUNT_NEAR_MISS", -1)) == 1
    assert any("engine_exclusion_audit_run123.csv" in path for path in artifact_list)
    assert seen["config"] == {
        "run_id": "run123",
        "profile_context": "dev_smoke",
        "binary_feature_engine_scope": "lifecycle_included",
    }


def test_av_analysis_pipeline_preserves_engine_scoring_exception(monkeypatch) -> None:
    """Engine scoring exceptions should surface as explicit stage errors, not empty score tables."""
    samples_df = pd.DataFrame({"sample_id": [1, 2]})
    monkeypatch.setattr(
        av_engine_pipeline.av_binary_matrix_builder,
        "generate_binary_detection_matrix",
        lambda *_args, **_kwargs: pd.DataFrame({"sample_id": [1, 2], "EngineA": [1, 0]}),
    )
    monkeypatch.setattr(
        av_engine_pipeline.enrich_scores,
        "apply_score_enrichment",
        lambda df, **_kwargs: df.copy(),
    )
    monkeypatch.setattr(
        av_engine_pipeline,
        "attach_engine_metadata",
        lambda df, **_kwargs: df.copy(),
    )

    def boom(*_args, **_kwargs):
        raise NameError("ml_console is not defined")

    monkeypatch.setattr(av_engine_pipeline, "run_av_engine_scoring", boom)

    result = av_engine_pipeline.run_av_analysis_pipeline(samples_df, verbose=False)

    assert result["engine_scores"] is None
    assert result["error"] == "Engine scoring error (NameError): ml_console is not defined"


def test_apply_binary_feature_scope_preserves_default_and_gates_experiment() -> None:
    """The lifecycle experiment must be explicit and must not alter the baseline."""
    matrix = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "Engine A": [1, 0],
            "Engine_B": [0, 1],
            "Engine C": [1, 1],
        }
    )
    lifecycle = pd.DataFrame(
        {
            "engine_name_canonical": ["engine_a", "engine_b", "engine_c"],
            "included_in_model_flag": [True, True, False],
        }
    )

    baseline, baseline_contract = av_engine_pipeline.apply_binary_feature_engine_scope(
        matrix,
        lifecycle,
        scope="all_observed",
    )
    gated, gated_contract = av_engine_pipeline.apply_binary_feature_engine_scope(
        matrix,
        lifecycle,
        scope="lifecycle_included",
    )

    assert baseline.columns.tolist() == matrix.columns.tolist()
    assert baseline_contract["selected_binary_engine_columns"] == 3
    assert gated.columns.tolist() == ["sample_id", "Engine A", "Engine_B"]
    assert gated_contract == {
        "binary_feature_engine_scope": "lifecycle_included",
        "observed_binary_engine_columns": 3,
        "selected_binary_engine_columns": 2,
        "lifecycle_included_engine_count": 2,
        "excluded_binary_engine_columns": 1,
    }


def test_av_analysis_pipeline_applies_lifecycle_scope_before_enrichment(monkeypatch) -> None:
    """Enrichment must receive the declared scoped matrix, not the raw universe."""
    samples_df = pd.DataFrame({"sample_id": [1, 2]})
    raw_matrix = pd.DataFrame(
        {"sample_id": [1, 2], "engine_a": [1, 0], "engine_b": [0, 1]}
    )
    lifecycle = pd.DataFrame(
        {
            "engine_name_canonical": ["engine_a", "engine_b"],
            "included_in_model_flag": [True, False],
        }
    )
    score_df = pd.DataFrame({"engine_name": ["engine_a", "engine_b"]})
    score_df.attrs["engine_lifecycle"] = lifecycle
    seen: dict[str, list[str]] = {}

    monkeypatch.setattr(
        av_engine_pipeline.av_binary_matrix_builder,
        "generate_binary_detection_matrix",
        lambda *_args, **_kwargs: raw_matrix.copy(),
    )
    monkeypatch.setattr(
        av_engine_pipeline,
        "run_av_engine_scoring",
        lambda *_args, **_kwargs: score_df,
    )

    def capture_enrichment(frame, **_kwargs):
        seen["columns"] = frame.columns.tolist()
        return frame.copy()

    monkeypatch.setattr(av_engine_pipeline.enrich_scores, "apply_score_enrichment", capture_enrichment)
    monkeypatch.setattr(av_engine_pipeline, "attach_engine_metadata", lambda frame, **_kwargs: frame)

    result = av_engine_pipeline.run_av_analysis_pipeline(
        samples_df,
        config={"binary_feature_engine_scope": "lifecycle_included"},
        verbose=False,
    )

    assert result["error"] is None
    assert seen["columns"] == ["sample_id", "engine_a"]
    assert result["av_binary_feature_scope_contract"]["selected_binary_engine_columns"] == 1


def test_av_selection_contract_joins_lifecycle_parser_and_final_features(tmp_path) -> None:
    """The audit artifact must distinguish parser selection from model membership."""
    lifecycle = pd.DataFrame(
        {
            "engine_name_canonical": ["engine_a", "engine_b"],
            "included_in_model_flag": [True, False],
        }
    )
    weights = pd.DataFrame(
        {
            "Vendor": ["engine_a"],
            "included_in_model": [1],
            "Leakage Safe Score Raw": [0.7],
            "Leakage Safe Score": [0.7],
            "Final ML Score": [0.2],
        }
    )

    path = export_av_selection_contract(
        lifecycle_df=lifecycle,
        weights_df=weights,
        binary_feature_columns=["engine_a", "engine_b"],
        final_feature_columns=["engine_a", "perm__example"],
        selected_vendors=["engine_a"],
        selected_vendor_predictive_field_count=0,
        binary_scope_contract={"binary_feature_engine_scope": "all_observed"},
        diagnostics_dir=tmp_path,
        run_id="run123",
        profile_id="profile123",
    )

    contract = pd.read_csv(path)
    row_a = contract.loc[contract["engine_name_canonical"] == "engine_a"].iloc[0]
    row_b = contract.loc[contract["engine_name_canonical"] == "engine_b"].iloc[0]
    assert row_a["selected_parser_vendor"] == 1
    assert row_a["binary_column_retained_for_headline_training"] == 1
    assert row_b["selected_parser_vendor"] == 0
    assert row_b["binary_column_retained_for_headline_training"] == 0
    assert set(contract["selected_vendor_predictive_field_count"]) == {0}
