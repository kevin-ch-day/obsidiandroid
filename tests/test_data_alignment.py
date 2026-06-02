"""Tests for explicit alignment failure semantics and non-mutating behavior."""

from __future__ import annotations

import pandas as pd
import pytest

from obsidiandroid.modeling import data_alignment
from obsidiandroid.feature_engineering import pattern_analysis


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


def test_extract_aligned_labels_promotes_sample_id_column_under_range_index() -> None:
    """When the matrix still has a default RangeIndex, row identity must come from ``sample_id``."""
    features_df = pd.DataFrame(
        {"sample_id": [101, 102], "feat": [1.0, 2.0]},
        index=pd.RangeIndex(2),
    )
    samples_df = pd.DataFrame(
        {
            "sample_id": [101, 102],
            "family_id": [1, 2],
            "family_canonical": ["FluBot", "SpyNote"],
        }
    )
    aligned, labels = data_alignment.extract_aligned_labels(
        features_df,
        samples_df,
        drop_low_support=False,
        verbose=False,
    )
    assert list(aligned.index) == ["101", "102"]
    assert len(labels) == 2
    assert list(labels.astype(str)) == ["1", "2"]


def test_extract_aligned_labels_with_family_id_filters_non_authoritative_family_canonical_labels() -> None:
    """Family IDs tied to non-authoritative family names should be dropped before training."""
    features_df = pd.DataFrame(
        {"sample_id": [101, 102, 103, 104], "feat": [1.0, 2.0, 3.0, 4.0]},
        index=pd.RangeIndex(4),
    )
    samples_df = pd.DataFrame(
        {
            "sample_id": [101, 102, 103, 104],
            "family_id": [1, 2, 3, 4],
            "family_canonical": ["FluBot", "SpyNote", "generic", "metasploit"],
        }
    )
    aligned, labels = data_alignment.extract_aligned_labels(
        features_df,
        samples_df,
        drop_low_support=False,
        verbose=False,
    )

    assert list(aligned.index) == ["101", "102"]
    assert list(labels.astype(str)) == ["1", "2"]


def test_extract_aligned_labels_with_family_id_filters_non_authoritative_aliases() -> None:
    """Family-canonical aliases should resolve and unknown tokens should be dropped."""
    features_df = pd.DataFrame(
        {
            "sample_id": [101, 102, 103, 104, 105],
            "feat": [1.0, 2.0, 3.0, 4.0, 5.0],
        },
        index=pd.RangeIndex(5),
    )
    samples_df = pd.DataFrame(
        {
            "sample_id": [101, 102, 103, 104, 105],
            "family_id": [1, 2, 3, 4, 5],
            "family_canonical": [
                "FluBot",
                "Cabassous",
                "metasploit",
                "some_unknown_token",
                "SpyNote",
            ],
        }
    )
    aligned, labels = data_alignment.extract_aligned_labels(
        features_df,
        samples_df,
        drop_low_support=False,
        verbose=False,
    )

    assert list(aligned.index) == ["101", "102", "105"]
    assert list(labels.astype(str)) == ["1", "2", "5"]


def test_extract_aligned_labels_with_family_id_retains_live_authority_family_outside_local_registry() -> None:
    """Live authoritative family rows should survive even if the local registry lags behind."""
    features_df = pd.DataFrame(
        {
            "sample_id": [101, 102, 103, 104],
            "feat": [1.0, 2.0, 3.0, 4.0],
        },
        index=pd.RangeIndex(4),
    )
    samples_df = pd.DataFrame(
        {
            "sample_id": [101, 102, 103, 104],
            "family_id": [1, 2, 3, 4],
            "family_canonical": ["FluBot", "Applite", "Wroba", "Piom"],
            "family_name": ["FluBot", "Applite", "Wroba", "Piom"],
            "sample_label_kind": [
                "family_or_common_name",
                "family_or_common_name",
                "family_or_common_name",
                "family_or_common_name",
            ],
            "type_slug": ["banker", "banker", "banker", "banker"],
        }
    )
    aligned, labels = data_alignment.extract_aligned_labels(
        features_df,
        samples_df,
        drop_low_support=False,
        verbose=False,
    )

    assert list(aligned.index) == ["101", "102", "103", "104"]
    assert list(labels.astype(str)) == ["1", "2", "3", "4"]
    stats = labels.attrs.get("alignment_attrition_stats", {})
    assert stats.get("alignment_non_authoritative_family_drop_count") == 0
    assert stats.get("alignment_live_authority_rescue_count") == 2
    assert stats.get("alignment_rows_post_authority_filter") == 4
    details = labels.attrs.get("alignment_attrition_details", {})
    assert details.get("alignment_live_authority_rescue_families") == {
        "Applite": 1,
        "Piom": 1,
    }


def test_extract_aligned_labels_does_not_retain_unknown_family_without_live_authority_support() -> None:
    """The live-authority fallback should stay narrow and reject unsupported unknown tokens."""
    features_df = pd.DataFrame(
        {
            "sample_id": [101, 102, 103],
            "feat": [1.0, 2.0, 3.0],
        },
        index=pd.RangeIndex(3),
    )
    samples_df = pd.DataFrame(
        {
            "sample_id": [101, 102, 103],
            "family_id": [1, 2, 3],
            "family_canonical": ["FluBot", "some_unknown_token", "SpyNote"],
            "family_name": ["FluBot", "", "SpyNote"],
            "sample_label_kind": ["family_or_common_name", "family_or_common_name", "family_or_common_name"],
            "type_slug": ["banker", "banker", "rat"],
        }
    )
    aligned, labels = data_alignment.extract_aligned_labels(
        features_df,
        samples_df,
        drop_low_support=False,
        verbose=False,
    )

    assert list(aligned.index) == ["101", "103"]
    assert list(labels.astype(str)) == ["1", "3"]
    details = labels.attrs.get("alignment_attrition_details", {})
    assert details.get("alignment_non_authoritative_family_drop_families") == {
        "some_unknown_token": 1,
    }


def test_extract_aligned_labels_retains_matching_family_authority_even_if_label_kind_is_stale() -> None:
    """Weak label kinds should not veto a row when the raw family label already matches authority."""
    features_df = pd.DataFrame(
        {
            "sample_id": [101, 102],
            "feat": [1.0, 2.0],
        },
        index=pd.RangeIndex(2),
    )
    samples_df = pd.DataFrame(
        {
            "sample_id": [101, 102],
            "family_id": [1, 2],
            "family_canonical": ["SpyNote", "FluBot"],
            "family_name": ["SpyNote", "FluBot"],
            "sample_label_kind": ["opaque_string", "family_or_common_name"],
            "type_slug": ["rat", "banker"],
        }
    )
    aligned, labels = data_alignment.extract_aligned_labels(
        features_df,
        samples_df,
        drop_low_support=False,
        verbose=False,
    )

    assert list(aligned.index) == ["101", "102"]
    assert list(labels.astype(str)) == ["1", "2"]


def test_emit_live_authority_retention_note_only_once_during_ablation(monkeypatch) -> None:
    printed: list[str] = []
    monkeypatch.setattr(data_alignment.app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    monkeypatch.setattr(data_alignment.app_config, "RUNTIME_ABLATION_AUTHORITY_NOTE_EMITTED", False, raising=False)
    monkeypatch.setattr(data_alignment.du, "print_info", lambda msg, *_a, **_k: printed.append(str(msg)))

    data_alignment._emit_live_authority_retention_note(159)  # pylint: disable=protected-access
    data_alignment._emit_live_authority_retention_note(159)  # pylint: disable=protected-access

    assert printed == [
        "Authority note: 159 live-authority-backed sample(s) retained despite local registry drift."
    ]


def test_feature_correlation_summary_runs() -> None:
    df = pd.DataFrame({"a": [1, 2, 3], "b": [2, 4, 6], "c": [1, 1, 1]})
    corr = pattern_analysis.feature_correlation_summary(df, verbose=False)
    assert isinstance(corr, pd.DataFrame)
    assert set(corr.columns) >= {"a", "b"}


def test_detect_outliers_basic() -> None:
    df = pd.DataFrame({"a": [1, 2, 100], "b": [1, 1, 1]})
    out = pattern_analysis.detect_outliers(df, ["a", "b"], z_thresh=1.0, verbose=False)
    assert len(out) == 1


def test_compute_pca_features_shape() -> None:
    df = pd.DataFrame({"a": [1, 2, 3], "b": [2, 4, 6]})
    result = pattern_analysis.compute_pca_features(df, n_components=1, verbose=False)
    assert "PCA_1" in result.columns
