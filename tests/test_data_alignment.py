"""Tests for explicit alignment failure semantics and non-mutating behavior."""

from __future__ import annotations

import pandas as pd
import pytest

from ml_classification.training import data_alignment


def test_extract_aligned_labels_raises_on_missing_sample_ids_without_mutating_inputs() -> None:
    """Alignment should raise a typed mismatch error and leave caller-owned frames unchanged."""
    features_df = pd.DataFrame({"feat": [1, 2]}, index=[101, 102])
    samples_df = pd.DataFrame(
        {
            "sample_id": [201, 202],
            "family_id": [1, 2],
            "family_canonical": ["FamA", "FamB"],
        }
    )
    original_index = list(features_df.index)

    with pytest.raises(data_alignment.SampleIdMismatchError):
        data_alignment.extract_aligned_labels(features_df, samples_df)

    assert list(features_df.index) == original_index


def test_extract_aligned_labels_raises_on_missing_sample_id_column() -> None:
    """Alignment should fail fast with a typed missing-column error."""
    features_df = pd.DataFrame({"feat": [1, 2]}, index=[101, 102])
    samples_df = pd.DataFrame(
        {
            "family_id": [1, 2],
            "family_canonical": ["FamA", "FamB"],
        }
    )

    with pytest.raises(data_alignment.MissingSampleIdColumnError):
        data_alignment.extract_aligned_labels(features_df, samples_df)
