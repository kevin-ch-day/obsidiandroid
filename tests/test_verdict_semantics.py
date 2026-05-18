"""Tests for shared AV verdict semantics across SQL and matrix builders."""

from __future__ import annotations

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
