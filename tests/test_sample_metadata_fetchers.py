"""Tests for SQL contract behavior in sample metadata fetchers."""

from __future__ import annotations

import re

from obsidiandroid.database import db_sample_metadata_fetchers as fetchers


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
        if "SUM(CASE WHEN base.sha256 IS NULL OR LENGTH(TRIM(base.sha256)) <> 64 THEN 1 ELSE 0 END) AS missing_sha256" in text:
            return (
                [
                    "total_candidates",
                    "missing_sha256",
                    "missing_hash_registry",
                    "unmapped_family",
                    "missing_package",
                    "unknown_type_slug",
                    "weak_label_kind_rows",
                    "family_label_conflict_rows",
                    "low_support_rows",
                ],
                [(100, 7, 5, 3, 2, 0, 0, 0, 4)],
            )
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
    assert any("LEFT JOIN" in q and "x.sha256 = y.sha256" in q for q in seen_queries)
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


def test_fetch_samples_by_type_applies_sql_family_cap_before_limit(monkeypatch) -> None:
    """Limited cohorts should cap families in SQL before the global limit is applied."""
    captured: dict[str, object] = {}

    def _fake_execute_query(query, **kwargs):
        captured["query"] = query
        captured["kwargs"] = kwargs
        return (["sample_id"], [(1,)])

    monkeypatch.setattr(fetchers.db_engine, "execute_query", _fake_execute_query)
    fetchers.fetch_samples_by_type(
        type_slug=None,
        limit=1200,
        family_cap=60,
        family_cap_seed=1337,
    )

    query = str(captured["query"])
    params = tuple(captured["kwargs"]["params"])
    assert "ROW_NUMBER() OVER" in query
    assert "PARTITION BY COALESCE(CAST(base.family_id AS CHAR)" in query
    assert "_family_loader_rn <= %s" in query
    assert "CRC32(CONCAT(%s, ':'" in query
    assert params[-2:] == (60, 1200)


def test_fetch_samples_by_type_applies_sql_type_cap_before_limit(monkeypatch) -> None:
    """Limited cohorts should cap types in SQL before the global limit is applied."""
    captured: dict[str, object] = {}

    def _fake_execute_query(query, **kwargs):
        captured["query"] = query
        captured["kwargs"] = kwargs
        return (["sample_id"], [(1,)])

    monkeypatch.setattr(fetchers.db_engine, "execute_query", _fake_execute_query)
    fetchers.fetch_samples_by_type(
        type_slug=None,
        limit=1200,
        family_cap=60,
        family_cap_seed=1337,
        type_cap=300,
        type_cap_seed=1337,
    )

    query = str(captured["query"])
    params = tuple(captured["kwargs"]["params"])
    assert "_type_loader_rn <= %s" in query
    assert "PARTITION BY COALESCE(LOWER(TRIM(COALESCE(family_capped.type_slug, ''))), '<blank>')" in query
    assert "CRC32(CONCAT(%s, ':'" in query
    assert params[-3:] == (60, 300, 1200)


def test_fetch_samples_by_type_applies_sql_type_cap_by_slug_before_limit(monkeypatch) -> None:
    """Limited cohorts should support explicit per-type quotas before the global limit."""
    captured: dict[str, object] = {}

    def _fake_execute_query(query, **kwargs):
        captured["query"] = query
        captured["kwargs"] = kwargs
        return (["sample_id"], [(1,)])

    monkeypatch.setattr(fetchers.db_engine, "execute_query", _fake_execute_query)
    fetchers.fetch_samples_by_type(
        type_slug=None,
        limit=1200,
        family_cap=60,
        family_cap_seed=1337,
        type_cap=220,
        type_cap_seed=1337,
        type_cap_by_slug={"banker": 140, "rat": 90},
    )

    query = str(captured["query"])
    params = tuple(captured["kwargs"]["params"])
    assert "_type_loader_rn <= CASE" in query
    assert "_type_slug_cap_probe" in query
    assert "WHEN LOWER(TRIM(COALESCE(_type_slug_cap_probe, ''))) = %s THEN %s" in query
    assert params[-7:] == ("banker", 140, "rat", 90, 220, 1200) or params[-7:] == (60, "banker", 140, "rat", 90, 220, 1200)


def test_fetch_samples_by_type_can_exclude_weak_and_conflicted_labels_in_sql(monkeypatch) -> None:
    """Limited profiles should be able to demand cleaner taxonomy rows at SQL time."""
    captured: dict[str, object] = {}

    def _fake_execute_query(query, **kwargs):
        captured["query"] = query
        captured["kwargs"] = kwargs
        return (["sample_id"], [(1,)])

    monkeypatch.setattr(fetchers.db_engine, "execute_query", _fake_execute_query)
    fetchers.fetch_samples_by_type(
        type_slug=None,
        exclude_weak_label_kinds=True,
        exclude_family_label_conflicts=True,
    )

    query = str(captured["query"])
    assert "sample_label_kind" in query
    assert "NOT IN ('filename', 'hash_like', 'opaque_string', 'unclassified')" in query
    assert "LOWER(TRIM(COALESCE(y.family_label, ''))) <>" in query


def test_gate_stats_reports_quality_exclusions_when_enabled(monkeypatch) -> None:
    """Gate stats should surface weak-label and family-conflict exclusion buckets."""
    def _fake_execute_query(query, params=None, **_kwargs):
        text = str(query)
        if "cohort_governed_count" in text:
            return (["c"], [(91,)])
        if "SUM(CASE WHEN base.sha256 IS NULL OR LENGTH(TRIM(base.sha256)) <> 64 THEN 1 ELSE 0 END) AS missing_sha256" in text:
            return (
                [
                    "total_candidates",
                    "missing_sha256",
                    "missing_hash_registry",
                    "unmapped_family",
                    "missing_package",
                    "unknown_type_slug",
                    "weak_label_kind_rows",
                    "family_label_conflict_rows",
                    "low_support_rows",
                ],
                [(100, 0, 0, 0, 0, 0, 6, 3, 0)],
            )
        return (["c"], [(100,)])

    monkeypatch.setattr(fetchers.db_engine, "execute_query", _fake_execute_query)
    stats = fetchers.get_type_cohort_gate_stats(
        type_slug=None,
        exclude_weak_label_kinds=True,
        exclude_family_label_conflicts=True,
    )

    assert stats["excluded_weak_label_kind"] == 6
    assert stats["excluded_family_label_conflict"] == 3


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
        if "SUM(CASE WHEN base.sha256 IS NULL OR LENGTH(TRIM(base.sha256)) <> 64 THEN 1 ELSE 0 END) AS missing_sha256" in text:
            return (
                [
                    "total_candidates",
                    "missing_sha256",
                    "missing_hash_registry",
                    "unmapped_family",
                    "missing_package",
                    "unknown_type_slug",
                    "low_support_rows",
                ],
                [(100, 0, 0, 0, 0, 11, 0)],
            )
        return (["c"], [(100,)])

    monkeypatch.setattr(fetchers.db_engine, "execute_query", _fake_execute_query)
    stats = fetchers.get_type_cohort_gate_stats(
        type_slug=None,
        exclude_unknown_type_slug=True,
    )

    assert stats["excluded_unknown_type_slug"] == 11
    assert stats["governed_cohort_count"] == 89
    assert stats["final_count_estimate"] == 89


def test_catalog_semantics_profile_uses_governed_android_loader_scope(monkeypatch) -> None:
    """SQL semantics profiler should return grouped Android cohort drift metrics."""
    seen_queries: list[str] = []

    def _fake_execute_query(query, params=None, **_kwargs):
        text = str(query)
        seen_queries.append(text)
        if "GROUP BY group_label" in text:
            return (
                [
                    "group_label",
                    "rows",
                    "non_android_lane_rows",
                    "non_android_payload_target_rows",
                    "weak_label_rows",
                    "blank_family_raw_with_vt_token_rows",
                    "raw_family_vs_canonical_conflict_rows",
                    "issue_events",
                ],
                [("banker", 3, 1, 1, 2, 0, 1, 5)],
            )
        if "SUM(CASE WHEN LOWER(TRIM(analysis_lane)) <> 'android_artifact'" in text:
            return (
                [
                    "non_android_lane_rows",
                    "non_android_payload_target_rows",
                    "hash_like_label_rows",
                    "opaque_label_rows",
                    "unclassified_label_rows",
                    "filename_label_rows",
                    "vt_family_token_rows",
                    "blank_family_raw_with_vt_token_rows",
                    "weak_label_with_canonical_family_rows",
                    "raw_family_vs_canonical_conflict_rows",
                ],
                [(7, 6, 5, 4, 3, 2, 9, 8, 1, 11)],
            )
        if "GROUP BY label" in text:
            return (["label", "c"], [("android_artifact", 9), ("windows_targeting_non_windows", 1)])
        return (["c"], [(0,)])

    monkeypatch.setattr(fetchers.db_engine, "execute_query", _fake_execute_query)
    profile = fetchers.get_type_cohort_catalog_semantics_profile(
        type_slug=None,
        exclude_unknown_type_slug=True,
    )

    assert profile["scope"] == "sql_governed_android_cohort"
    assert profile["non_android_lane_rows"] == 7
    assert profile["non_android_payload_target_rows"] == 6
    assert profile["hash_like_label_rows"] == 5
    assert profile["filename_label_rows"] == 2
    assert profile["raw_family_vs_canonical_conflict_rows"] == 11
    assert profile["sample_label_kind_distribution"]["android_artifact"] == 9
    assert profile["top_drift_types"][0]["type_slug"] == "banker"
    joined = " ".join(seen_queries)
    assert "WHERE y.platform = 'android'" in joined
    assert "COALESCE(LOWER(TRIM(t.type_slug)), '') <> 'unknown'" in joined
    assert "COUNT(*) AS row_count" in joined
    assert "ORDER BY issue_events DESC, row_count DESC, group_label ASC" in joined
