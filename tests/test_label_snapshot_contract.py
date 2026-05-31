"""Tests for shared label snapshot normalization and hashing."""

from __future__ import annotations

import pandas as pd

from obsidiandroid.governance.label_snapshot_contract import (
    label_snapshot_hash,
    normalize_label_snapshot_frame,
)


def test_normalize_label_snapshot_frame_adds_optional_columns_and_sorts() -> None:
    df = pd.DataFrame(
        {
            "sample_id": ["2", "1", "1"],
            "family_canonical": ["FamB", "FamA", "FamA"],
            "type_slug": ["spyware", "banker", "banker"],
        }
    )

    out = normalize_label_snapshot_frame(df)

    assert out is not None
    assert out["sample_id"].tolist() == [1, 2]
    assert out["sha256"].tolist() == ["", ""]
    assert list(out.columns) == ["sample_id", "sha256", "family_id", "family_canonical", "type_slug"]


def test_label_snapshot_hash_is_stable_across_row_order_and_noise() -> None:
    df1 = pd.DataFrame(
        {
            "sample_id": [2, 1],
            "sha256": ["b" * 64, "a" * 64],
            "family_id": [11, 10],
            "family_canonical": ["FamB", "FamA"],
            "type_slug": ["Spyware", "Banker"],
        }
    )
    df2 = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "sha256": ["a" * 64, "b" * 64],
            "family_id": [10, 11],
            "family_canonical": [" FamA ", "FamB"],
            "type_slug": ["banker", "spyware"],
        }
    )

    assert label_snapshot_hash(df1) == label_snapshot_hash(df2)
