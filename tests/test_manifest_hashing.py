"""Tests for deterministic manifest hashing helpers."""

from __future__ import annotations

import pandas as pd

from analysis.pipeline.manifest.hashing import (
    canonical_csv_bytes,
    dataset_hash_from_sample_ids,
    sha256_hex,
)


def test_dataset_hash_from_sample_ids_is_order_stable() -> None:
    """Dataset hash should be independent of input order."""
    left = dataset_hash_from_sample_ids([3, 1, 2])
    right = dataset_hash_from_sample_ids([2, 3, 1])
    assert left == right


def test_canonical_csv_bytes_is_stable_for_same_values() -> None:
    """Canonical CSV bytes should be deterministic."""
    frame = pd.DataFrame(
        [
            {"rank": 1, "engine_id": "a", "score": 0.5},
            {"rank": 2, "engine_id": "b", "score": 0.1},
        ]
    )
    one = canonical_csv_bytes(
        frame,
        columns=["rank", "engine_id", "score"],
        float_format="%.6f",
        lineterminator="\n",
    )
    two = canonical_csv_bytes(
        frame[["rank", "engine_id", "score"]],
        float_format="%.6f",
        lineterminator="\n",
    )
    assert one == two
    assert b"\r\n" not in one


def test_sha256_hex_matches_canonical_bytes() -> None:
    """Hash helper should produce stable digest from canonical bytes."""
    frame = pd.DataFrame([{"x": 1.23456789}, {"x": 2.0}])
    payload = canonical_csv_bytes(frame, float_format="%.6f", lineterminator="\n")
    digest = sha256_hex(payload)
    assert len(digest) == 64
    assert digest == sha256_hex(payload)

