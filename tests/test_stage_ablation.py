"""Tests for ablation pipeline utility helpers."""

import pandas as pd

from analysis.pipeline import stage_ablation
from config import app_config


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
        return kwargs["features_df"], kwargs["labels_df"], 0, 0

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
