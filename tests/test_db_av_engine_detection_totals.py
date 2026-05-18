"""Tests for AV engine detection-total SQL helpers."""

from __future__ import annotations

from obsidiandroid.database import db_av_engine_detection_totals as totals


def test_union_sql_nulls_non_detection_tokens() -> None:
    sql = totals._build_union_sql(["google"])  # pylint: disable=protected-access

    assert "WHEN `google` IS NULL" in sql
    assert "'type-unsupported'" in sql
    assert "THEN NULL" in sql
    assert "ELSE `google`" in sql


def test_engine_stats_query_counts_positive_non_benign_detections() -> None:
    sql = totals._build_engine_stats_query("SELECT 'google' AS engine_name, 'Detected' AS result")  # pylint: disable=protected-access

    assert "SUM(" in sql
    assert "melted.result IS NOT NULL" in sql
    assert "NOT LOWER(TRIM(melted.result)) REGEXP 'benign|clean|safe|trusted|approved|verified|whitelist'" in sql
    assert "AS malicious_count" in sql
    assert "AS threat_signal_score" in sql
    assert "AS unknown_count" in sql


def test_family_name_hits_regex_uses_current_family_taxonomy_and_aliases() -> None:
    regex = totals._family_name_hits_regex()  # pylint: disable=protected-access

    assert "crocodilus" in regex
    assert "zanubis" in regex
    assert "flu-bot" in regex
    assert "gold digger" in regex
