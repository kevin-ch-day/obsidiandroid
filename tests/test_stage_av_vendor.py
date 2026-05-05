"""Tests for AV/vendor stage helper utilities."""

import pandas as pd
import pytest

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

    monkeypatch.setattr(
        stage_av_vendor.av_engine_pipeline,
        "run_av_analysis_pipeline",
        lambda *_args, **_kwargs: {"engine_scores": scores_df, "engine_lifecycle": lifecycle_df},
    )

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
