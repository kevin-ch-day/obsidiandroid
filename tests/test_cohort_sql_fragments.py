"""SQL fragments for cardinality-safe cohort joins."""

from __future__ import annotations

from obsidiandroid.database.cohort_sql_fragments import (
    latest_family_resolution_subquery,
    latest_vt_scan_summary_subquery,
)


def test_vt_scan_summary_subquery_uses_row_number_per_sample_id() -> None:
    sql = latest_vt_scan_summary_subquery()
    assert "ROW_NUMBER()" in sql
    assert "PARTITION BY s0.sample_id" in sql
    assert "virustotal_sample_scan_summary" in sql


def test_family_resolution_subquery_uses_row_number_per_sample_id() -> None:
    sql = latest_family_resolution_subquery()
    assert "ROW_NUMBER()" in sql
    assert "PARTITION BY v0.sample_id" in sql
    assert "v_android_apk_family_resolved" in sql
