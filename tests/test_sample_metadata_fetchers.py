"""Tests for SQL contract behavior in sample metadata fetchers."""

from __future__ import annotations

import re

from database import db_sample_metadata_fetchers as fetchers


def test_fetch_samples_by_type_uses_left_hash_join_when_sha_not_required(monkeypatch) -> None:
    """Fetcher should not force hash-registry inner join when SHA is optional."""
    captured: dict[str, object] = {}

    def _fake_execute_query(query, **kwargs):
        captured["query"] = query
        captured["kwargs"] = kwargs
        return (["sample_id"], [(1,)])

    monkeypatch.setattr(fetchers.db_engine, "execute_query", _fake_execute_query)
    fetchers.fetch_samples_by_type(type_slug="banker", require_sha256=False)

    query = str(captured["query"])
    m = re.search(r"(?P<left>LEFT )?JOIN \s*\(\s*SELECT z\.\*", query, re.DOTALL)
    assert m and m.group("left") is not None
    assert "malware_artifact_hash_registry h0" in query
    assert "_artifact_hash_rn" in query


def test_fetch_samples_by_type_uses_inner_hash_join_when_sha_required(monkeypatch) -> None:
    """Fetcher should enforce hash-registry inner join when SHA is required."""
    captured: dict[str, object] = {}

    def _fake_execute_query(query, **kwargs):
        captured["query"] = query
        captured["kwargs"] = kwargs
        return (["sample_id"], [(1,)])

    monkeypatch.setattr(fetchers.db_engine, "execute_query", _fake_execute_query)
    fetchers.fetch_samples_by_type(type_slug="banker", require_sha256=True)

    query = str(captured["query"])
    m = re.search(r"(?P<left>LEFT )?JOIN \s*\(\s*SELECT z\.\*", query, re.DOTALL)
    assert m and m.group("left") is None
    assert "malware_artifact_hash_registry h0" in query
    assert "_artifact_hash_rn" in query


def test_gate_stats_accounts_for_missing_hash_registry_rows(monkeypatch) -> None:
    """Gate stats should include hash-registry exclusion in final estimate."""
    seen_queries: list[str] = []

    def _fake_execute_query(query, params=None, **_kwargs):
        text = str(query)
        seen_queries.append(text)
        if "cohort_governed_count" in text:
            return (["c"], [(79,)])
        if "COALESCE(SUM(cnt), 0) AS c" in text:
            return (["c"], [(4,)])
        if "x.sha256 IS NULL" in text:
            return (["c"], [(5,)])
        if "y.sha256 IS NULL OR LENGTH(TRIM(y.sha256)) <> 64" in text:
            return (["c"], [(7,)])
        if "f.family_id IS NULL" in text:
            return (["c"], [(3,)])
        if "COALESCE(TRIM(y.android_package_name), '') = ''" in text:
            return (["c"], [(2,)])
        return (["c"], [(100,)])

    monkeypatch.setattr(fetchers.db_engine, "execute_query", _fake_execute_query)
    stats = fetchers.get_type_cohort_gate_stats(
        type_slug="banker",
        min_samples_per_family=3,
        require_mapped_family=True,
        require_sha256=True,
        allow_missing_package_name=False,
    )

    assert any("malware_artifact_hash_registry h0" in q and "_artifact_hash_rn" in q for q in seen_queries)
    assert stats["excluded_missing_sha256"] == 7
    assert stats["excluded_missing_hash_registry"] == 5
    assert stats["governed_cohort_count"] == 79
    assert stats["final_count_estimate"] == 79
    assert stats["final_count_estimate_sequential_legacy"] == 79


def test_fetch_min_support_subquery_reuses_sha_join_mode(monkeypatch) -> None:
    """Min-support family subquery should honor require_sha256 join semantics."""
    captured: dict[str, object] = {}

    def _fake_execute_query(query, **kwargs):
        captured["query"] = query
        captured["kwargs"] = kwargs
        return (["sample_id"], [(1,)])

    monkeypatch.setattr(fetchers.db_engine, "execute_query", _fake_execute_query)
    fetchers.fetch_samples_by_type(
        type_slug="banker",
        min_samples_per_family=3,
        require_sha256=False,
    )

    query = str(captured["query"])
    m = re.search(r"(?P<left>LEFT )?JOIN \s*\(\s*SELECT z\.\*", query, re.DOTALL)
    assert m and m.group("left") is not None
    assert "x_inner.sha256 = y_inner.sha256" in query
    assert "malware_artifact_hash_registry h0" in query
    assert query.count("_artifact_hash_rn") >= 2


def test_gate_stats_query_uses_same_scan_summary_join_as_fetch(monkeypatch) -> None:
    """Gate stats base relation should include scan-summary join used by fetch query."""
    seen_queries: list[str] = []

    def _fake_execute_query(query, params=None, **_kwargs):
        seen_queries.append(str(query))
        return (["c"], [(0,)])

    monkeypatch.setattr(fetchers.db_engine, "execute_query", _fake_execute_query)
    fetchers.get_type_cohort_gate_stats(type_slug="banker")

    joined = " ".join(seen_queries)
    assert "ROW_NUMBER()" in joined
    assert "virustotal_sample_scan_summary" in joined
    assert "v_android_apk_family_resolved" in joined


def test_fetch_samples_by_type_excludes_unknown_type_slug_in_sql(monkeypatch) -> None:
    """Fetcher should apply unknown-type exclusion at SQL layer when requested."""
    captured: dict[str, object] = {}

    def _fake_execute_query(query, **kwargs):
        captured["query"] = query
        return (["sample_id"], [(1,)])

    monkeypatch.setattr(fetchers.db_engine, "execute_query", _fake_execute_query)
    fetchers.fetch_samples_by_type(
        type_slug=None,
        exclude_unknown_type_slug=True,
    )

    query = str(captured["query"])
    assert "COALESCE(LOWER(TRIM(t.type_slug)), '') <> 'unknown'" in query
    assert "COALESCE(TRIM(t.type_slug), '') <> ''" in query


def test_gate_stats_reports_unknown_type_exclusions_when_enabled(monkeypatch) -> None:
    """Gate stats should account for unknown type exclusions when gate is enabled."""
    def _fake_execute_query(query, params=None, **_kwargs):
        text = str(query)
        if "cohort_governed_count" in text:
            return (["c"], [(89,)])
        if "COALESCE(SUM(cnt), 0) AS c" in text:
            return (["c"], [(0,)])
        if "COALESCE(LOWER(TRIM(t.type_slug)), '') = 'unknown'" in text:
            return (["c"], [(11,)])
        if "f.family_id IS NULL" in text:
            return (["c"], [(0,)])
        if "y.sha256 IS NULL OR LENGTH(TRIM(y.sha256)) <> 64" in text:
            return (["c"], [(0,)])
        if "x.sha256 IS NULL" in text:
            return (["c"], [(0,)])
        if "COALESCE(TRIM(y.android_package_name), '') = ''" in text:
            return (["c"], [(0,)])
        return (["c"], [(100,)])

    monkeypatch.setattr(fetchers.db_engine, "execute_query", _fake_execute_query)
    stats = fetchers.get_type_cohort_gate_stats(
        type_slug=None,
        exclude_unknown_type_slug=True,
    )

    assert stats["excluded_unknown_type_slug"] == 11
    assert stats["governed_cohort_count"] == 89
    assert stats["final_count_estimate"] == 89
