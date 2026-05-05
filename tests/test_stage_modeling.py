"""Tests for modeling stage helper functions."""

import pandas as pd

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
