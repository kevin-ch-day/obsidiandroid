"""Tests for shared AV verdict semantics across SQL and matrix builders."""

from __future__ import annotations

import numpy as np
import pandas as pd

from obsidiandroid.database import db_av_disagreement_analysis
from obsidiandroid.database import db_av_engine_verdicts
from obsidiandroid.database import db_fetch_av_engine_raw_results
from obsidiandroid.database import db_utils
from obsidiandroid.database import verdict_semantics
from obsidiandroid.matrix import av_binary_matrix_builder


def test_positive_detection_labels_include_generic_positive_tokens() -> None:
    assert verdict_semantics.is_positive_detection_label("Detected") == 1
    assert verdict_semantics.is_positive_detection_label("unsafe") == 1
    assert verdict_semantics.is_positive_detection_label("Malicious (score: 99)") == 1
    assert verdict_semantics.is_positive_detection_label("undetected") == 0
    assert verdict_semantics.is_positive_detection_label("type-unsupported") == 0
    assert verdict_semantics.is_positive_detection_label("clean") == 0


def test_binary_matrix_positive_detection_uses_shared_semantics() -> None:
    assert av_binary_matrix_builder._is_positive_detection("Detected") == 1  # pylint: disable=protected-access
    assert av_binary_matrix_builder._is_positive_detection("Android:Evo-gen [Trj]") == 1  # pylint: disable=protected-access
    assert av_binary_matrix_builder._is_positive_detection("undetected") == 0  # pylint: disable=protected-access


def test_disagreement_union_sql_classifies_raw_labels_before_aggregation() -> None:
    sql = db_av_disagreement_analysis.build_melt_union_sql(["google"])

    assert "CASE" in sql
    assert "THEN 'undetected'" in sql
    assert "ELSE 'malicious'" in sql
    assert "FROM virustotal_sample_vendor_engine_verdicts" in sql


def test_wide_verdict_metadata_columns_are_shared_across_helpers() -> None:
    assert db_av_engine_verdicts.METADATA_COLS == verdict_semantics.VERDICT_METADATA_COLUMNS
    assert av_binary_matrix_builder.METADATA_COLS == verdict_semantics.VERDICT_METADATA_COLUMNS
    assert db_utils.AV_ENGINES_RESULTS_IGNORED_COLS == verdict_semantics.VERDICT_METADATA_COLUMNS
    assert db_fetch_av_engine_raw_results.COLUMNS_TO_EXCLUDE == (
        verdict_semantics.VERDICT_METADATA_COLUMNS - {"sample_id"}
    )


def test_binary_matrix_vectorized_conversion_preserves_verdict_semantics(monkeypatch) -> None:
    wide = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "engine_a": ["Detected", "undetected"],
            "engine_b": [None, "clean"],
            "engine_c": ["type-unsupported", "Android:Evo-gen [Trj]"],
        }
    )
    monkeypatch.setattr(
        av_binary_matrix_builder.db_av_engine_verdicts,
        "fetch_verdicts_simple_ids",
        lambda *_args, **_kwargs: wide,
    )

    out = av_binary_matrix_builder._generate_av_binary_matrix(  # pylint: disable=protected-access
        pd.DataFrame({"sample_id": [1, 2]}), verbose=False
    )

    assert out.set_index("sample_id").to_dict(orient="list") == {
        "engine_a": [1, 0],
        "engine_b": [0, 0],
        "engine_c": [0, 1],
    }
    assert out.attrs["engine_scan_counts"] == {"engine_a": 2, "engine_b": 1, "engine_c": 2}


def test_binary_matrix_direct_builder_matches_melt_pivot_duplicate_and_null_contract(monkeypatch) -> None:
    wide = pd.DataFrame(
        {
            "sample_id": [2, 1, 2, 3],
            "engine_a": ["undetected", "Detected", "Detected", None],
            "engine_b": [None, "clean", "Android:Evo-gen [Trj]", None],
        }
    )
    monkeypatch.setattr(
        av_binary_matrix_builder.db_av_engine_verdicts,
        "fetch_verdicts_simple_ids",
        lambda *_args, **_kwargs: wide,
    )
    direct = av_binary_matrix_builder._generate_av_binary_matrix(  # pylint: disable=protected-access
        pd.DataFrame({"sample_id": [1, 2, 3]}), verbose=False
    )

    long = av_binary_matrix_builder.convert_to_long_format(wide)
    expected = (
        long.assign(value=long["result"].map(av_binary_matrix_builder._is_positive_detection))  # pylint: disable=protected-access
        .pivot_table(index="sample_id", columns="engine_name", values="value", aggfunc="max", fill_value=0)
        .astype("int8")
        .reset_index()
    )
    pd.testing.assert_frame_equal(direct, expected)


def test_binary_matrix_cleanup_preserves_compact_binary_dtype() -> None:
    out = av_binary_matrix_builder._postprocess_and_clean_matrix(  # pylint: disable=protected-access
        pd.DataFrame({"sample_id": [1, 2], "engine_a": [1, 0], "engine_b": [0, 1]})
    )
    assert out["engine_a"].dtype == np.dtype("int8")
    assert out["engine_b"].dtype == np.dtype("int8")
