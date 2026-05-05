"""Tests for ablation pipeline utility helpers."""

import numpy as np
import pandas as pd

from obsidiandroid.pipeline import stage_ablation
from config import app_config
from obsidiandroid.modeling import model_trainer_factory


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
