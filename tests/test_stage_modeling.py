"""Tests for modeling stage helper functions."""

import pandas as pd

from config import app_config
from obsidiandroid.pipeline import stage_modeling


def test_run_training_stage_returns_none_when_trainer_fails(monkeypatch) -> None:
    """Training stage should return ``None`` when trainer yields no results."""

    def _fake_train_all_models(*args, **kwargs):
        return None

    monkeypatch.setattr(
        stage_modeling.pipeline_core,
        "train_all_models",
        _fake_train_all_models,
    )

    features_df = pd.DataFrame({"f": [0.1, 0.2]})
    labels_df = pd.DataFrame({"family": ["a", "b"]})

    result = stage_modeling.run_training_stage(
        aligned_feature_df=features_df,
        aligned_labels_df=labels_df,
        model_list=["xgboost"],
    )

    assert result is None


def test_resolve_final_labels_stage_rejects_missing_predictions() -> None:
    """Label resolution should return ``None`` if predictions are missing."""
    result = stage_modeling.resolve_final_labels_stage(
        vendor_records={},
        model_output={"model": "xgboost"},
    )
    assert result is None


def test_enrich_vendor_trust_flags_merges_engine_scores() -> None:
    """Trusted/active flags should be merged onto vendor weights by normalized vendor key."""
    weights_df = pd.DataFrame(
        {
            "Vendor": ["lionic", "drweb", "unknown_vendor"],
            "Final ML Score": [0.2, 0.3, 0.1],
        }
    )
    engine_scores_df = pd.DataFrame(
        {
            "Engine Name": ["lionic", "dr_web"],
            "Trusted": [1, 0],
            "Active": [1, 1],
        }
    )

    out = stage_modeling._enrich_vendor_trust_flags(  # pylint: disable=protected-access
        weights_df=weights_df,
        engine_scores_df=engine_scores_df,
    )

    assert "trusted_vendor_flag" in out.columns
    assert "active_vendor_flag" in out.columns
    lionic = out[out["Vendor"] == "lionic"].iloc[0]
    drweb = out[out["Vendor"] == "drweb"].iloc[0]
    unknown = out[out["Vendor"] == "unknown_vendor"].iloc[0]
    assert int(lionic["trusted_vendor_flag"]) == 1
    assert int(drweb["trusted_vendor_flag"]) == 0
    assert int(unknown["trusted_vendor_flag"]) == 0


def test_engine_weight_stage_skips_db_summary_when_primary_scores_exist(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "ENABLE_ENGINE_WEIGHT_DB_SUMMARY", True, raising=False)
    called = {"db_summary": False}

    def unexpected_db_summary():
        called["db_summary"] = True
        raise AssertionError("DB fallback must not run when primary scores are available")

    monkeypatch.setattr(
        stage_modeling.engine_scoring_summary,
        "build_av_engine_scoring_summary_from_db",
        unexpected_db_summary,
    )
    monkeypatch.setattr(
        stage_modeling.compute_vendor_scores,
        "run_score_analysis",
        lambda _df, verbose: pd.DataFrame({"Vendor": ["lionic"], "Final ML Score": [0.2]}),
    )

    out = stage_modeling.compute_engine_weights_from_pipeline(
        {
            "vendor_eval_df": pd.DataFrame({"Vendor": ["lionic"]}),
            "engine_scores": pd.DataFrame(
                {"Engine Name": ["lionic"], "Trusted": [1], "Active": [1]}
            ),
        }
    )

    assert out is not None
    assert called["db_summary"] is False
    assert int(out.loc[0, "trusted_vendor_flag"]) == 1


def test_engine_weight_stage_uses_db_summary_as_missing_primary_score_fallback(monkeypatch) -> None:
    monkeypatch.setattr(app_config, "ENABLE_ENGINE_WEIGHT_DB_SUMMARY", True, raising=False)
    monkeypatch.setattr(
        stage_modeling.engine_scoring_summary,
        "build_av_engine_scoring_summary_from_db",
        lambda: pd.DataFrame({"engine_name": ["lionic"]}),
    )
    monkeypatch.setattr(
        stage_modeling.compute_vendor_scores,
        "run_score_analysis",
        lambda _df, verbose: pd.DataFrame({"Vendor": ["lionic"], "Final ML Score": [0.2]}),
    )
    pipeline_results = {"vendor_eval_df": pd.DataFrame({"Vendor": ["lionic"]})}

    out = stage_modeling.compute_engine_weights_from_pipeline(pipeline_results)

    assert out is not None
    assert "engine_summary" in pipeline_results


def test_resolve_vendor_include_fields_defaults_to_no_label_derived_vendor_fields(monkeypatch) -> None:
    """Headline family classification must not receive parsed vendor labels by default."""
    monkeypatch.setattr(app_config, "ENABLE_LABEL_DERIVED_VENDOR_FEATURES", False, raising=False)
    assert stage_modeling._resolve_vendor_include_fields() == []


def test_resolve_vendor_include_fields_requires_explicit_opt_in(monkeypatch) -> None:
    """Label-derived vendor fields remain available only for a scoped experiment."""
    monkeypatch.setattr(app_config, "ENABLE_LABEL_DERIVED_VENDOR_FEATURES", True, raising=False)
    assert stage_modeling._resolve_vendor_include_fields() == [
        "Parsed Family",
        "Threat Class",
        "Malware Type",
    ]


def test_safe_feature_contract_explains_that_vendor_top_k_is_not_used(monkeypatch) -> None:
    """Do not make a parser Top-K setting look like a headline feature input."""
    monkeypatch.setattr(app_config, "ENABLE_LABEL_DERIVED_VENDOR_FEATURES", False, raising=False)
    monkeypatch.setattr(app_config, "ENABLE_LEAKAGE_SAFE_VENDOR_SCORING", False, raising=False)
    messages: list[str] = []
    monkeypatch.setattr(stage_modeling.du, "print_info", lambda message: messages.append(str(message)))
    monkeypatch.setattr(stage_modeling.du, "print_success", lambda _message: None)
    matrix = pd.DataFrame({"perm__camera": [1]}, index=pd.Index([7], name="sample_id"))
    matrix.attrs.update(
        {
            "selected_vendors": [],
            "vendor_fallback_used": False,
            "vendor_fallback_added_count": 0,
            "vendor_selection_policy": "parser_disabled_no_predictive_fields",
        }
    )
    monkeypatch.setattr(
        stage_modeling.feature_vector_builder,
        "build_feature_vector",
        lambda **_kwargs: matrix,
    )

    out = stage_modeling.build_feature_matrix_stage(
        weights_df=pd.DataFrame({"Vendor": ["engine_a"]}),
        vendor_data={},
        cohort_sample_ids=[7],
    )

    assert out is matrix
    assert any("Top-K selection is not a headline-model input" in message for message in messages)
    assert any("0 predictive columns by policy" in message for message in messages)
