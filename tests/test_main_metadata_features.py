"""Tests for metadata feature extraction (pipeline sample preparation)."""

import pandas as pd

from analysis.pipeline.sample_preparation import build_metadata_feature_frame


def test_build_metadata_feature_frame_creates_expected_columns() -> None:
    """VT metadata columns should be transformed into ML-safe features."""
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "permissions": [10, 20],
            "vt_malicious_count": [5, 1],
            "vt_suspicious_count": [1, 0],
            "vt_undetected_count": [4, 9],
            "vt_tags": ["banker,overlay", '["spy","rat"]'],
            "vt_suggested_threat_label": ["banker", ""],
            "android_package_name": ["com.a", None],
        }
    )

    out = build_metadata_feature_frame(samples_df)
    assert "sample_id" in out.columns
    assert "meta__permissions" in out.columns
    assert "meta__vt_tag_count" in out.columns
    assert "meta__has_android_package_name" in out.columns
    assert "meta__has_vt_suggested_threat_label" in out.columns
    assert "meta__vt_positive_ratio" in out.columns

    # Tag counting should handle both comma-separated strings and JSON lists.
    assert out.loc[out["sample_id"] == 1, "meta__vt_tag_count"].iloc[0] == 2
    assert out.loc[out["sample_id"] == 2, "meta__vt_tag_count"].iloc[0] == 2


def test_orchestration_metadata_features_shim_matches_canonical() -> None:
    """``analysis.orchestration.metadata_features`` delegates to ``sample_preparation``."""
    import analysis.orchestration.metadata_features as shim
    import analysis.pipeline.sample_preparation as canon

    assert shim.build_metadata_feature_frame is canon.build_metadata_feature_frame
    assert shim.extract_vt_tag_count is canon.extract_vt_tag_count