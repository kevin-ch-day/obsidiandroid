"""Tests for prediction_builder metadata propagation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.modeling import prediction_builder


def test_export_model_backfills_named_feature_importances_into_result_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        prediction_builder.model_exporter,
        "export_model_to_file",
        lambda **_kwargs: tmp_path / "dummy.joblib",
    )
    result = {
        "metadata": {
            "feature_importances": [(1, 0.7), (0, 0.3)],
        },
        "label_classes": ["fam_a"],
        "label_name_map": {},
    }
    features_df = pd.DataFrame({"perm__internet": [1], "parsed_family_vendor": [0]})

    prediction_builder.export_model(
        result,
        "random_forest",
        features_df,
        {"accuracy": 1.0},
        tmp_path,
    )

    named = result["metadata"]["feature_importances_named"]
    assert named[0]["feature_name"] == "parsed_family_vendor"
    assert named[1]["feature_name"] == "perm__internet"
