"""Regression tests for low-support family handling in pipeline_core."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import app_config
from ml_classification.training import pipeline_core


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
        return kwargs["features_df"], kwargs["labels_df"], 0, 0

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
