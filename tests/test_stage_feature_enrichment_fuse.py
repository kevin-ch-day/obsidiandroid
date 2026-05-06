"""Tests for permission + metadata fusion keyed on ``sample_id`` (not row position)."""

from __future__ import annotations

import pandas as pd

from obsidiandroid.features import feature_vector_builder
from obsidiandroid.pipeline import stage_feature_enrichment as sfe
from ml_classification.vectorization.feature_encoder import encode_features


def test_merge_sample_metadata_fuses_permissions_by_sample_id_not_position() -> None:
    """Permission columns must attach to matching ``sample_id`` after metadata merge + dedupe."""
    samples_df = pd.DataFrame(
        {
            "sample_id": [495, 579, 657],
            "permissions": [12, 0, 8],
        }
    )
    enriched = pd.DataFrame(
        {
            "sample_id": [495, 579, 657],
            "malicious_ratio": [0.4, 0.5, 0.6],
        }
    )
    permission_features_df = pd.DataFrame(
        {
            "sample_id": [495, 657],
            "perm__android_permission_internet": [1, 1],
            "perm__android_permission_wake_lock": [1, 0],
            "perm__total_count": [4, 2],
        }
    )
    flags = {"enable_sample_metadata_features": True}
    merged = sfe.merge_sample_metadata_features(
        enriched,
        samples_df,
        flags,
        permission_features_df,
    )
    assert merged is not None
    assert not merged.empty
    assert sorted(merged["sample_id"].tolist()) == [495, 579, 657]
    assert int(merged.loc[merged["sample_id"] == 495, "perm__android_permission_internet"].iloc[0]) == 1
    assert int(merged.loc[merged["sample_id"] == 657, "perm__android_permission_internet"].iloc[0]) == 1
    wake_579 = int(merged.loc[merged["sample_id"] == 579, "perm__android_permission_wake_lock"].iloc[0])
    assert wake_579 == 0
    assert int(merged.loc[merged["sample_id"] == 579, "perm__total_count"].iloc[0]) == 0


def test_merge_sample_metadata_coerces_string_sample_id_for_permission_join() -> None:
    """String ``sample_id`` values on the AV enrichment base must still join PI permission rows."""
    samples_df = pd.DataFrame({"sample_id": [495, 657], "permissions": [1, 2]})
    enriched = pd.DataFrame({"sample_id": ["495", "657"], "malicious_ratio": [0.1, 0.2]})
    permission_features_df = pd.DataFrame(
        {
            "sample_id": [495, 657],
            "perm__android_permission_internet": [1, 1],
        }
    )
    merged = sfe.merge_sample_metadata_features(
        enriched,
        samples_df,
        {"enable_sample_metadata_features": True},
        permission_features_df,
    )
    assert merged is not None
    assert merged["sample_id"].dtype == "int64"
    assert int(merged.loc[merged["sample_id"] == 495, "perm__android_permission_internet"].iloc[0]) == 1


def test_merge_sample_metadata_drops_overlay_rows_before_permission_fuse() -> None:
    """Rows without a numeric catalog ``sample_id`` (e.g. engine-metadata overlays) must not dilute joins."""
    samples_df = pd.DataFrame({"sample_id": [495, 657], "permissions": [3, 4]})
    enriched = pd.DataFrame(
        {
            "sample_id": [495, float("nan"), 657, float("nan")],
            "malicious_ratio": [0.1, 9.9, 0.2, 8.8],
        }
    )
    permission_features_df = pd.DataFrame(
        {
            "sample_id": [495, 657],
            "perm__android_permission_internet": [1, 1],
        }
    )
    merged = sfe.merge_sample_metadata_features(
        enriched,
        samples_df,
        {"enable_sample_metadata_features": True},
        permission_features_df,
    )
    assert merged is not None
    assert set(merged["sample_id"].tolist()) == {495, 657}
    assert int(merged.loc[merged["sample_id"] == 495, "perm__android_permission_internet"].iloc[0]) == 1


def test_merge_extra_features_aligns_perm_columns_by_encoded_index() -> None:
    """End-to-end: encoded vendor matrix index ids receive ``perm__`` values from enrichment by ``sample_id``."""
    vendor_merged = pd.DataFrame(
        {
            "sample_id": [495, 579, 657],
            "parsed_family_vendorx": ["a", "b", "c"],
        }
    )
    encoded = encode_features(vendor_merged, encoding="category", verbose=False, skip_numeric=True)
    samples_df = pd.DataFrame({"sample_id": [495, 579, 657], "permissions": [2, 2, 2]})
    enriched = pd.DataFrame({"sample_id": [495, 579, 657], "malicious_ratio": [0.3, 0.4, 0.5]})
    permission_features_df = pd.DataFrame(
        {
            "sample_id": [495, 657],
            "perm__android_permission_internet": [1, 1],
            "perm__total_count": [3, 5],
        }
    )
    extra = sfe.merge_sample_metadata_features(
        enriched,
        samples_df,
        {"enable_sample_metadata_features": True},
        permission_features_df,
    )
    out, _maps = feature_vector_builder._merge_extra_features(encoded, extra, verbose=False)
    internet_cols = [c for c in out.columns if "internet" in str(c).lower() and str(c).startswith("perm__")]
    assert internet_cols, f"expected perm internet column, got {out.columns.tolist()}"
    col = internet_cols[0]
    assert int(out.loc[495, col]) > 0
    assert int(out.loc[657, col]) > 0
    assert int(out.loc[579, col]) == 0
