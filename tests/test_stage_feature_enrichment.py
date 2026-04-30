"""Tests for feature enrichment stage helpers."""

from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.pipeline import stage_feature_enrichment


def test_merge_sample_metadata_features_disabled_returns_original() -> None:
    """Disabled flag should bypass metadata frame generation."""
    existing_df = pd.DataFrame({"sample_id": [1], "existing": [1.0]})
    samples_df = pd.DataFrame({"sample_id": [1], "permissions": [2]})

    result = stage_feature_enrichment.merge_sample_metadata_features(
        extra_features_df=existing_df,
        samples_df=samples_df,
        feature_flags={"enable_sample_metadata_features": False},
    )

    assert result is existing_df


def test_merge_sample_metadata_features_merges_expected_columns() -> None:
    """Enabled flag should merge metadata-derived columns by sample id."""
    existing_df = pd.DataFrame({"sample_id": [1, 2], "existing": [1.0, 2.0]})
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "permissions": [10, 20],
            "vt_tags": ["banker,overlay", ""],
        }
    )

    result = stage_feature_enrichment.merge_sample_metadata_features(
        extra_features_df=existing_df,
        samples_df=samples_df,
        feature_flags={"enable_sample_metadata_features": True},
    )

    assert isinstance(result, pd.DataFrame)
    assert "meta__permissions" in result.columns
    assert "meta__vt_tag_count" in result.columns
    assert result.shape[0] == 2
