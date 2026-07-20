"""Database layer tests: engine smoke, schema map, split Erebus + Permission Intel config."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

from mysql.connector import Error as MySQLError
import pandas as pd
import pytest

from obsidiandroid.database import authority_contracts, db_engine, schema_map, verdict_contracts
import obsidiandroid.database.db_errors as db_errors
import obsidiandroid.database.db_permission_analysis_queries as db_permission_analysis_queries
from obsidiandroid.database import cohort_sql_fragments
import obsidiandroid.database.db_extract_av_label_keywords as db_extract_av_label_keywords
from obsidiandroid.database import db_config
from obsidiandroid.database.db_config import DB_NAME, PERMISSION_INTEL_DB_NAME
from obsidiandroid.database.db_permission_analysis_queries import (
    fetch_android_banking_trojans_with_permissions_count,
    fetch_android_banking_trojans_with_permissions,
    fetch_av_report_by_sample_id,
)
from obsidiandroid.database.db_sample_timelines_queries import (
    fetch_family_sample_timeline,
    fetch_global_sample_timeline,
    fetch_samples_by_year,
    summarize_family_timelines,
)
from obsidiandroid.database.settings import ObsidianConnectionSettings, load_connection_settings


def test_test_connection_does_not_raise_unboundlocal_on_connect_failure(monkeypatch) -> None:
    """Connection smoke test should swallow connector errors without masking them."""

    def _raise(*_args, **_kwargs):
        raise MySQLError("boom")

    monkeypatch.setattr(db_engine.mysql.connector, "connect", _raise)
    assert db_engine.test_connection(verbose=False) is False


def test_connect_with_localhost_fallback_retries_via_tcp_loopback(monkeypatch) -> None:
    """localhost socket-style failures should retry once against 127.0.0.1."""
    calls: list[dict] = []

    class _Conn:
        def is_connected(self) -> bool:
            return True

    def fake_connect(**kwargs):
        calls.append(dict(kwargs))
        if kwargs["host"] == "localhost":
            exc = MySQLError("Can't connect to local server through socket '/var/lib/mysql/mysql.sock' (1)")
            exc.errno = 2002
            raise exc
        return _Conn()

    monkeypatch.setattr(db_engine.mysql.connector, "connect", fake_connect)

    conn = db_engine._connect_with_localhost_fallback(  # pylint: disable=protected-access
        {
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "pw",
            "database": "db",
        },
        database_name="db",
    )

    assert conn.is_connected() is True
    assert [call["host"] for call in calls] == ["localhost", "127.0.0.1"]


def test_connect_with_localhost_fallback_does_not_retry_non_localhost(monkeypatch) -> None:
    """Non-localhost connection failures should bubble without a TCP-loopback retry."""
    calls: list[dict] = []

    def fake_connect(**kwargs):
        calls.append(dict(kwargs))
        exc = MySQLError("network down")
        exc.errno = 2003
        raise exc

    monkeypatch.setattr(db_engine.mysql.connector, "connect", fake_connect)

    with pytest.raises(MySQLError):
        db_engine._connect_with_localhost_fallback(  # pylint: disable=protected-access
            {
                "host": "db.example.internal",
                "port": 3306,
                "user": "root",
                "password": "pw",
                "database": "db",
            },
            database_name="db",
        )

    assert [call["host"] for call in calls] == ["db.example.internal"]


def test_primary_option_file_is_an_explicit_private_source_configuration(monkeypatch, tmp_path: Path) -> None:
    option_file = tmp_path / "source.cnf"
    option_file.write_text("[client]\n", encoding="utf-8")
    option_file.chmod(0o600)
    monkeypatch.setattr(db_engine, "DB_OPTION_FILE", str(option_file))
    monkeypatch.setattr(db_engine, "DB_HOST", "")
    monkeypatch.setattr(db_engine, "DB_USER", "")
    monkeypatch.setattr(db_engine, "DB_PASSWORD", "")
    kwargs = db_engine._build_connect_kwargs()
    assert kwargs["option_files"] == str(option_file)
    assert kwargs["database"] == db_engine.DB_NAME


def test_execute_permission_query_retries_permission_intel_localhost_via_tcp(monkeypatch) -> None:
    """Permission Intel DB helpers should inherit the same localhost fallback behavior."""
    calls: list[dict] = []

    class _Cursor:
        description = None

        def execute(self, *_args, **_kwargs):
            return None

        def close(self):
            return None

    class _Conn:
        def cursor(self):
            return _Cursor()

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

        def is_connected(self) -> bool:
            return True

    def fake_connect(**kwargs):
        calls.append(dict(kwargs))
        if kwargs["host"] == "localhost":
            exc = MySQLError("Can't connect to local server through socket '/var/lib/mysql/mysql.sock' (1)")
            exc.errno = 2002
            raise exc
        return _Conn()

    monkeypatch.setattr(db_engine.mysql.connector, "connect", fake_connect)
    monkeypatch.setattr(db_engine, "PERMISSION_INTEL_DB_HOST", "localhost")
    monkeypatch.setattr(db_engine, "PERMISSION_INTEL_DB_USER", "fixture_user")
    monkeypatch.setattr(db_engine, "PERMISSION_INTEL_DB_PASSWORD", "fixture_password")

    db_engine.execute_permission_query("SELECT 1", fetch=False)

    assert [call["host"] for call in calls] == ["localhost", "127.0.0.1"]


def test_mysql_error_summary_includes_errno_and_transient_flag() -> None:
    """Error helper should classify common MySQL transport failures as transient."""
    exc = MySQLError("server gone")
    exc.errno = 2006
    s = db_errors.mysql_error_summary(exc)
    assert s["errno"] == 2006
    assert s["transient"] is True
    assert "gone" in s["message"].lower() or "server" in s["message"].lower()


def test_mysql_error_summary_deadlock_is_transient() -> None:
    """Deadlocks should classify as transient for retry policy."""
    exc = MySQLError("deadlock")
    exc.errno = 1213
    assert db_errors.mysql_error_summary(exc)["transient"] is True
    assert db_errors.is_transient_mysql_error(exc) is True


def test_non_mysql_exception_summary() -> None:
    """Non-MySQL exceptions should be marked non-transient and keep type details."""
    s = db_errors.mysql_error_summary(ValueError("bad arg"))
    assert s["error_type"] == "ValueError"
    assert s["errno"] is None
    assert s["transient"] is False


def test_operator_facing_db_message_truncates() -> None:
    """Operator message should include error code and obey max length cap."""
    exc = MySQLError("x" * 500)
    exc.errno = 1146
    msg = db_errors.operator_facing_db_message(exc, max_len=80)
    assert len(msg) <= 80
    assert "1146" in msg


def test_load_connection_settings_matches_dataclass_fields() -> None:
    s = load_connection_settings()
    assert isinstance(s, ObsidianConnectionSettings)
    assert isinstance(s.host, str)
    assert isinstance(s.port, int)
    assert isinstance(s.database, str)
    assert isinstance(s.permission_intel_database, str)
    assert isinstance(s.core_database, str)
    assert s.core_database == db_config.CORE_DB_NAME
    assert s.core_database_host == db_config.CORE_DB_HOST
    assert s.core_database_port == db_config.CORE_DB_PORT
    assert s.core_database_user == db_config.CORE_DB_USER
    assert s.core_database_password == db_config.CORE_DB_PASSWORD
    assert s.core_persistence_enabled is db_config.CORE_PERSISTENCE_ENABLED


def test_schema_table_resolution():
    assert schema_map.table("vendor_engines") == "virustotal_vendor_engines"
    assert schema_map.table("vendor_verdicts") == "virustotal_sample_vendor_engine_verdicts"


def test_schema_column_resolution():
    assert schema_map.column("vendor_engines", "engine_name") == "vendor_key"
    assert schema_map.column("vendor_engines", "trusted_flag") == "is_trusted_vendor"
    assert schema_map.column("vendor_engines", "active_flag") == "is_engine_active"


def test_schema_compatible_column_resolution_prefers_canonical_then_legacy() -> None:
    assert schema_map.compatible_columns("vendor_label_generic_tokens", "active_flag") == (
        "is_active",
        "active_flag",
    )
    assert (
        schema_map.resolve_existing_column(
            "vendor_label_generic_tokens",
            "active_flag",
            {"normalized_token", "is_active"},
        )
        == "is_active"
    )
    assert (
        schema_map.resolve_existing_column(
            "vendor_label_generic_tokens",
            "active_flag",
            {"normalized_token", "active_flag"},
        )
        == "active_flag"
    )
    assert (
        schema_map.resolve_existing_column(
            "vendor_label_generic_tokens",
            "active_flag",
            {"normalized_token"},
        )
        is None
    )


def test_authority_view_present_requires_view_and_required_columns(monkeypatch) -> None:
    objects_df = pd.DataFrame(
        [
            {
                "table_name": schema_map.table("android_sample_family_type_authority_view"),
                "table_type": "VIEW",
            }
        ]
    )
    columns_df = pd.DataFrame(
        [
            {
                "table_name": schema_map.table("android_sample_family_type_authority_view"),
                "column_name": column_name,
            }
            for column_name in authority_contracts.LIVE_AUTHORITY_REQUIRED_COLUMNS[
                schema_map.table("android_sample_family_type_authority_view")
            ]
        ]
    )
    monkeypatch.setattr(authority_contracts, "fetch_objects_df", lambda: objects_df)
    monkeypatch.setattr(authority_contracts, "fetch_columns_df", lambda: columns_df)

    assert authority_contracts.authority_view_present() is True

    missing_df = columns_df[columns_df["column_name"] != "authority_gap_reason"].copy()
    monkeypatch.setattr(authority_contracts, "fetch_columns_df", lambda: missing_df)

    assert authority_contracts.authority_view_present() is False


def test_load_family_alias_map_prefers_legacy_when_canonical_missing(monkeypatch) -> None:
    def _fake_query(query: str, **_kwargs):
        if "FROM information_schema.tables" in query and "malware_family_alias_fact" in query:
            return pd.DataFrame([{"table_name": "x", "table_type": "BASE TABLE"}]).iloc[0:0]
        if "FROM information_schema.tables" in query and "android_malware_family_alias" in query:
            return pd.DataFrame([{"table_name": "android_malware_family_alias", "table_type": "BASE TABLE"}])
        if "FROM android_malware_family_alias AS a" in query:
            return pd.DataFrame(
                [
                    {"alias_token": "monocle", "canonical_family_slug": "monokle"},
                    {"alias_token": "spymax", "canonical_family_slug": "spynote"},
                ]
            )
        raise AssertionError(query)

    monkeypatch.setattr(authority_contracts, "fetch_objects_df", lambda: pd.DataFrame())
    monkeypatch.setattr(authority_contracts.db_engine, "execute_query", _fake_query)
    monkeypatch.setattr(
        authority_contracts,
        "authority_alias_fact_present",
        lambda: False,
    )
    monkeypatch.setattr(
        authority_contracts,
        "legacy_android_family_alias_present",
        lambda: True,
    )
    monkeypatch.setattr(authority_contracts, "table_has_column", lambda *_args, **_kwargs: False)

    out = authority_contracts.load_family_alias_map()

    assert out == {"monocle": "monokle", "spymax": "spynote"}


def test_load_family_alias_map_merges_canonical_and_legacy_sources(monkeypatch) -> None:
    def _fake_query(query: str, **_kwargs):
        if "FROM malware_family_alias_fact" in query:
            return pd.DataFrame(
                [
                    {"alias_token": "fakecalls", "canonical_family_slug": "fakecall"},
                    {"alias_token": "spymax", "canonical_family_slug": "spynote"},
                ]
            )
        if "FROM android_malware_family_alias AS a" in query:
            return pd.DataFrame(
                [
                    {"alias_token": "brats", "canonical_family_slug": "brata"},
                    {"alias_token": "spymax", "canonical_family_slug": "spynote"},
                ]
            )
        raise AssertionError(query)

    monkeypatch.setattr(authority_contracts, "authority_alias_fact_present", lambda: True)
    monkeypatch.setattr(authority_contracts, "legacy_android_family_alias_present", lambda: True)
    monkeypatch.setattr(authority_contracts, "table_has_column", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(authority_contracts.db_engine, "execute_query", _fake_query)

    out = authority_contracts.load_family_alias_map()

    assert out == {
        "fakecalls": "fakecall",
        "spymax": "spynote",
        "brats": "brata",
    }


def test_fetch_legacy_alias_df_filters_nonaccepted_and_inactive_rows(monkeypatch) -> None:
    seen_queries: list[str] = []

    def _fake_query(query: str, **_kwargs):
        seen_queries.append(query)
        return pd.DataFrame([{"alias_token": "wroba", "canonical_family_slug": "roamingmantis"}])

    def _fake_table_has_column(table_name: str, column_name: str) -> bool:
        return (table_name, column_name) in {
            ("android_malware_family_alias", "is_active"),
            ("android_malware_family_alias", "review_status"),
            ("android_malware_family", "is_active"),
        }

    monkeypatch.setattr(authority_contracts, "table_has_column", _fake_table_has_column)
    monkeypatch.setattr(authority_contracts.db_engine, "execute_query", _fake_query)

    out = authority_contracts._fetch_legacy_alias_df()

    assert out.to_dict(orient="records") == [
        {"alias_token": "wroba", "canonical_family_slug": "roamingmantis"}
    ]
    assert seen_queries
    query = seen_queries[0]
    assert "a.is_active = 1" in query
    assert "a.review_status = 'accepted'" in query
    assert "f.is_active = 1" in query


def test_load_known_family_and_alias_tokens_includes_parser_aliases_for_active_families(monkeypatch) -> None:
    monkeypatch.setattr(authority_contracts, "load_active_family_tokens", lambda: {"spynote", "gravityrat"})
    monkeypatch.setattr(authority_contracts, "load_family_alias_map", lambda: {"fakecalls": "fakecall"})

    families, aliases = authority_contracts.load_known_family_and_alias_tokens()

    assert families == {"spynote", "gravityrat"}
    assert "fakecalls" in aliases
    assert "spymax" in aliases
    assert "gravity_rat" in aliases


def test_vt_scan_summary_subquery_uses_row_number_per_sample_id() -> None:
    sql = cohort_sql_fragments.latest_vt_scan_summary_subquery()
    assert "ROW_NUMBER()" in sql
    assert "PARTITION BY s0.sample_id" in sql
    assert "virustotal_sample_scan_summary" in sql


def test_family_resolution_subquery_uses_row_number_per_sample_id() -> None:
    sql = cohort_sql_fragments.latest_family_resolution_subquery()
    assert "ROW_NUMBER()" in sql
    assert "PARTITION BY v0.sample_id" in sql
    assert "v_android_apk_family_resolved" in sql


def test_fetch_sample_authority_map_falls_back_without_live_view(monkeypatch) -> None:
    queries: list[str] = []

    def _fake_query(query: str, params=None, **_kwargs):
        queries.append(query)
        if "FROM malware_sample_catalog AS msc" in query:
            return pd.DataFrame(
                [
                    {
                        "sample_id": 99,
                        "authority_family_slug": "blankbot",
                        "authority_family_name": "blankbot",
                        "authority_type_slug": "banker",
                    }
                ]
            )
        raise AssertionError(query)

    monkeypatch.setattr(authority_contracts, "authority_view_present", lambda **_kwargs: False)
    monkeypatch.setattr(authority_contracts, "table_has_column", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(authority_contracts.db_engine, "execute_query", _fake_query)

    out = authority_contracts.fetch_sample_authority_map([99])

    assert len(out) == 1
    assert "FROM malware_sample_catalog AS msc" in queries[0]


def test_collect_raw_engine_labels_query_excludes_non_detection_tokens(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def fake_execute_query(query, **_kwargs):
        seen["query"] = query
        return ["result"], [("Detected",), ("Trojan.Android",)]

    monkeypatch.setattr(db_extract_av_label_keywords.db_engine, "execute_query", fake_execute_query)

    labels = db_extract_av_label_keywords.collect_raw_engine_labels("google", sample_limit=10)

    assert labels == ["Detected", "Trojan.Android"]
    assert "type-unsupported" in seen["query"]
    assert "undetected" in seen["query"]
    assert "WHERE NOT (" in seen["query"]


def test_fetch_vendor_verdict_columns_uses_shared_table_columns(monkeypatch) -> None:
    monkeypatch.setattr(
        verdict_contracts.db_engine,
        "get_table_columns",
        lambda table_name: ["sample_id", "updated_at", "kaspersky", "microsoft"],
    )

    assert verdict_contracts.fetch_verdict_table_columns() == [
        "sample_id",
        "updated_at",
        "kaspersky",
        "microsoft",
    ]
    assert verdict_contracts.fetch_vendor_verdict_columns() == ["kaspersky", "microsoft"]


def test_fetch_vendor_engine_flags_uses_schema_map_columns(monkeypatch) -> None:
    queries: list[str] = []

    def _fake_query(query: str, **_kwargs):
        queries.append(query)
        return pd.DataFrame(
            [
                {
                    "vendor_key": "kaspersky",
                    "is_engine_active": 1,
                    "is_trusted_vendor": 1,
                }
            ]
        )

    monkeypatch.setattr(verdict_contracts.db_engine, "execute_query", _fake_query)

    out = verdict_contracts.fetch_vendor_engine_flags()

    assert len(out) == 1
    assert "FROM virustotal_vendor_engines" in queries[0]
    assert "vendor_key" in queries[0]
    assert "is_engine_active" in queries[0]
    assert "is_trusted_vendor" in queries[0]


def test_load_active_family_tokens_uses_active_clause_when_available(monkeypatch) -> None:
    queries: list[str] = []

    def _fake_query(query: str, **_kwargs):
        queries.append(query)
        return pd.DataFrame([{"token": "blankbot"}, {"token": "bankbot"}])

    monkeypatch.setattr(authority_contracts, "table_has_column", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(authority_contracts.db_engine, "execute_query", _fake_query)

    out = authority_contracts.load_active_family_tokens()

    assert out == {"blankbot", "bankbot"}
    assert "AND is_active = 1" in queries[0]


def test_execute_permission_query_uses_permission_intel_database(monkeypatch) -> None:
    """Permission Intel helper must open connections to PERMISSION_INTEL_DB_NAME."""
    captured: dict = {}

    mock_conn = MagicMock()
    mock_conn.is_connected.return_value = True
    mock_cursor = MagicMock()
    mock_cursor.description = None
    mock_conn.cursor.return_value = mock_cursor

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return mock_conn

    monkeypatch.setattr(db_engine.mysql.connector, "connect", fake_connect)
    monkeypatch.setattr(db_engine, "PERMISSION_INTEL_DB_HOST", "localhost")
    monkeypatch.setattr(db_engine, "PERMISSION_INTEL_DB_USER", "fixture_user")
    monkeypatch.setattr(db_engine, "PERMISSION_INTEL_DB_PASSWORD", "fixture_password")
    db_engine.execute_permission_query("SELECT 1", fetch=False)
    assert captured.get("database") == PERMISSION_INTEL_DB_NAME


def test_run_query_does_not_mask_keyboard_interrupt_with_cursor_close_error() -> None:
    class _FakeCursor:
        description = None

        def execute(self, *_args, **_kwargs):
            raise KeyboardInterrupt()

        def close(self):
            raise MySQLError("Unread result found")

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

        def rollback(self):
            return None

    with pytest.raises(KeyboardInterrupt):
        db_engine._run_query(  # pylint: disable=protected-access
            _FakeConn(),
            "SELECT 1",
            fetch=False,
        )


def test_run_query_does_not_mask_lost_connection_with_rollback_error() -> None:
    class _FakeCursor:
        description = None

        def execute(self, *_args, **_kwargs):
            exc = MySQLError("Lost connection to MySQL server during query")
            exc.errno = 2013
            raise exc

        def close(self):
            return None

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

        def rollback(self):
            exc = MySQLError("Lost connection to MySQL server during query")
            exc.errno = 2013
            raise exc

    with pytest.raises(MySQLError) as excinfo:
        db_engine._run_query(  # pylint: disable=protected-access
            _FakeConn(),
            "SELECT 1",
            fetch=False,
        )

    assert "Lost connection to MySQL server during query" in str(excinfo.value)


def test_fetch_banking_trojans_sql_qualifies_primary_and_pi(monkeypatch) -> None:
    """Cross-schema banking trojan query must fully qualify both databases."""
    queries: list[str] = []

    def capture(query, *_args, **_kwargs):
        queries.append(query)
        return (["c"], [])

    monkeypatch.setattr(db_engine, "execute_query", capture)
    fetch_android_banking_trojans_with_permissions()
    sql = queries[0]
    assert f"`{DB_NAME}`.`malware_sample_catalog`" in sql
    assert f"`{PERMISSION_INTEL_DB_NAME}`.`android_permission_obs_sample`" in sql
    assert f"`{PERMISSION_INTEL_DB_NAME}`.`android_permission_dict_aosp`" in sql
    assert "ORDER BY ms.sample_id ASC, ops.observed_at_utc ASC, ops.permission_string ASC" in sql
    assert "'golddigger'" in sql
    assert "'crocodilus'" in sql


def test_fetch_banking_trojans_sql_prefers_permission_string_norm_when_available(monkeypatch) -> None:
    queries: list[str] = []

    def capture(query, *_args, **_kwargs):
        queries.append(query)
        return (["c"], [])

    db_permission_analysis_queries.permission_contracts.reset_permission_obs_norm_cache()
    monkeypatch.setattr(
        db_permission_analysis_queries.permission_contracts.db_engine,
        "get_table_columns",
        lambda _table: ["sample_id", "permission_string", "permission_string_norm"],
    )
    monkeypatch.setattr(db_engine, "execute_query", capture)
    fetch_android_banking_trojans_with_permissions()
    sql = queries[0]
    assert "permission_string_norm" in sql
    assert "COALESCE(NULLIF(TRIM(ops.permission_string_norm), ''), LOWER(TRIM(ops.permission_string)))" in sql


def test_fetch_banking_trojans_sql_falls_back_without_permission_string_norm(monkeypatch) -> None:
    queries: list[str] = []

    def capture(query, *_args, **_kwargs):
        queries.append(query)
        return (["c"], [])

    db_permission_analysis_queries.permission_contracts.reset_permission_obs_norm_cache()
    monkeypatch.setattr(
        db_permission_analysis_queries.permission_contracts.db_engine,
        "get_table_columns",
        lambda _table: ["sample_id", "permission_string"],
    )
    monkeypatch.setattr(db_engine, "execute_query", capture)
    fetch_android_banking_trojans_with_permissions()
    sql = queries[0]
    assert "permission_string_norm" not in sql
    assert "LOWER(TRIM(ops.permission_string)) = LOWER(TRIM(kp.constant_value))" in sql


def test_fetch_banking_trojans_count_sql_uses_same_family_universe(monkeypatch) -> None:
    """Count helper should stay aligned with the detail helper's banking-family filter."""
    queries: list[str] = []

    def capture(query, *_args, **_kwargs):
        queries.append(query)
        return (["c"], [])

    monkeypatch.setattr(db_engine, "execute_query", capture)
    fetch_android_banking_trojans_with_permissions_count()
    sql = queries[0]
    assert "'golddigger'" in sql
    assert "'crocodilus'" in sql
    assert "ORDER BY ms.sample_id ASC" in sql


def test_fetch_av_report_by_sample_id_qualifies_primary_verdict_table(monkeypatch) -> None:
    """Single-sample AV report helper should use the canonical primary-schema table name."""
    queries: list[str] = []

    def capture(query, *_args, **_kwargs):
        queries.append(query)
        return (["sample_id"], [])

    monkeypatch.setattr(db_engine, "execute_query", capture)
    fetch_av_report_by_sample_id(123)
    sql = queries[0]
    assert f"`{DB_NAME}`.`virustotal_sample_vendor_engine_verdicts`" in sql


def test_global_sample_timeline_sql_is_primary_qualified_and_deterministic(monkeypatch) -> None:
    """Global timeline query should normalize family aliases and use stable ordering."""
    queries: list[str] = []

    def capture(query, *_args, **_kwargs):
        queries.append(query)
        return (["sample_id"], [])

    monkeypatch.setattr(db_engine, "execute_query", capture)
    fetch_global_sample_timeline()
    sql = queries[0]
    assert f"`{DB_NAME}`.`malware_sample_catalog`" in sql
    assert "THEN 'FluBot'" in sql
    assert "ELSE TRIM(family_label)" in sql
    assert "ORDER BY vt_first_submission_at_utc ASC, sample_id ASC" in sql


def test_family_sample_timeline_sql_uses_canonical_family_filter(monkeypatch) -> None:
    """Family timeline query should normalize FluBot aliases before filtering."""
    queries: list[str] = []

    def capture(query, *_args, **_kwargs):
        queries.append(query)
        return (["sample_id"], [])

    monkeypatch.setattr(db_engine, "execute_query", capture)
    fetch_family_sample_timeline("flubot")
    sql = queries[0]
    assert f"`{DB_NAME}`.`malware_sample_catalog`" in sql
    assert "REPLACE(" in sql
    assert "'FluBot', 'flubot'" in sql
    assert "ORDER BY vt_first_submission_at_utc ASC, sample_id ASC" in sql


def test_summarize_family_timelines_sql_groups_on_trimmed_canonical_name(monkeypatch) -> None:
    """Family timeline summary should group on the same normalized family expression it selects."""
    queries: list[str] = []

    def capture(query, *_args, **_kwargs):
        queries.append(query)
        return (["family_name"], [])

    monkeypatch.setattr(db_engine, "execute_query", capture)
    summarize_family_timelines()
    sql = queries[0]
    assert f"`{DB_NAME}`.`malware_sample_catalog`" in sql
    assert "GROUP BY CASE WHEN LOWER(TRIM(family_label)) IN ('cabassous', 'flubot') THEN 'FluBot' ELSE TRIM(family_label) END" in sql
    assert "ORDER BY first_submission ASC, family_name ASC" in sql


def test_fetch_samples_by_year_sql_normalizes_family_aliases(monkeypatch) -> None:
    """Year-based timeline query should not regress to raw family_label values."""
    queries: list[str] = []

    def capture(query, *_args, **_kwargs):
        queries.append(query)
        return (["sample_id"], [])

    monkeypatch.setattr(db_engine, "execute_query", capture)
    fetch_samples_by_year(2025)
    sql = queries[0]
    assert f"`{DB_NAME}`.`malware_sample_catalog`" in sql
    assert "AS family_name" in sql
    assert "ELSE TRIM(family_label)" in sql
    assert "ORDER BY vt_first_submission_at_utc ASC, sample_id ASC" in sql


def test_get_table_columns_routes_android_permission_tables_to_pi(monkeypatch) -> None:
    """android_permission_* metadata must not use primary SHOW COLUMNS when PI holds the table."""
    primary_calls: list[str] = []
    pi_calls: list[str] = []

    def fake_primary(query, **_kwargs):
        primary_calls.append(query)
        return [["wrong"]]

    def fake_pi(query, **_kwargs):
        pi_calls.append(query)
        return [["sample_id"], ["observed_at_utc"]]

    monkeypatch.setattr(db_engine, "execute_query", fake_primary)
    monkeypatch.setattr(db_engine, "execute_permission_query", fake_pi)
    cols = db_engine.get_table_columns("android_permission_obs_sample")
    assert cols == ["sample_id", "observed_at_utc"]
    assert not primary_calls
    assert len(pi_calls) == 1
    assert "SHOW COLUMNS" in pi_calls[0]
    assert PERMISSION_INTEL_DB_NAME in pi_calls[0]
    assert "android_permission_obs_sample" in pi_calls[0]


def test_get_table_columns_uses_primary_for_catalog_tables(monkeypatch) -> None:
    pi_calls: list[str] = []

    def fake_primary(query, **_kwargs):
        assert "malware_sample_catalog" in query
        return [["sample_id"]]

    def fake_pi(*_args, **_kwargs):
        pi_calls.append("should_not_run")
        return []

    monkeypatch.setattr(db_engine, "execute_query", fake_primary)
    monkeypatch.setattr(db_engine, "execute_permission_query", fake_pi)
    assert db_engine.get_table_columns("malware_sample_catalog") == ["sample_id"]
    assert not pi_calls


def test_check_split_database_health_structure(monkeypatch) -> None:
    """Health report includes expected keys (connectivity mocked)."""
    monkeypatch.setattr(
        db_engine.mysql.connector,
        "connect",
        MagicMock(side_effect=MySQLError("no db")),
    )
    report = db_engine.check_split_database_health()
    assert {
        "primary_ok",
        "permission_intel_ok",
        "permission_obs_sample_in_pi",
        "primary_error",
        "permission_intel_error",
    }.issubset(set(report.keys()))
    assert report["primary_ok"] is False
    assert report["permission_intel_ok"] is False
    assert report["permission_obs_sample_in_pi"] is False
    assert isinstance(report.get("primary_error"), str)
    assert isinstance(report.get("permission_intel_error"), str)


def test_db_config_obsidian_env_overrides_in_fresh_interpreter() -> None:
    """OBSIDIAN_* env vars must override defaults (isolated process avoids import cache)."""
    repo_root = Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    script = textwrap.dedent(
        """
        import os
        import sys
        sys.path.insert(0, %r)
        sys.path.insert(0, %r)
        os.environ["OBSIDIAN_DB_NAME"] = "primary_from_env"
        os.environ["OBSIDIAN_PERMISSION_INTEL_DB_NAME"] = "pi_from_env"
        import obsidiandroid.database.db_config as cfg
        assert cfg.DB_NAME == "primary_from_env"
        assert cfg.PERMISSION_INTEL_DB_NAME == "pi_from_env"
        """
        % (str(repo_root), str(src_root))
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_db_config_erebus_env_fallbacks_in_fresh_interpreter() -> None:
    """Erebus-style env vars should be accepted for shared platform deployments."""
    repo_root = Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    script = textwrap.dedent(
        """
        import os
        import sys
        sys.path.insert(0, %r)
        sys.path.insert(0, %r)
        os.environ["EREBUS_DB_HOST"] = "erebus-db-host"
        os.environ["EREBUS_DB_PORT"] = "4406"
        os.environ["EREBUS_DB_USER"] = "erebus_user"
        os.environ["EREBUS_DB_PASSWORD"] = "erebus_pw"
        os.environ["EREBUS_DB_NAME"] = "erebus_primary"
        os.environ["EREBUS_PERMISSION_INTEL_DB_NAME"] = "erebus_pi"
        os.environ["EREBUS_PERMISSION_INTEL_DB_HOST"] = "erebus-pi-host"
        os.environ["EREBUS_PERMISSION_INTEL_DB_PORT"] = "5506"
        os.environ["EREBUS_PERMISSION_INTEL_DB_USER"] = "erebus_pi_user"
        os.environ["EREBUS_PERMISSION_INTEL_DB_PASSWORD"] = "erebus_pi_pw"
        import obsidiandroid.database.db_config as cfg
        assert cfg.DB_HOST == "erebus-db-host"
        assert cfg.DB_PORT == 4406
        assert cfg.DB_USER == "erebus_user"
        assert cfg.DB_PASSWORD == "erebus_pw"
        assert cfg.DB_NAME == "erebus_primary"
        assert cfg.PERMISSION_INTEL_DB_NAME == "erebus_pi"
        assert cfg.PERMISSION_INTEL_DB_HOST == "erebus-pi-host"
        assert cfg.PERMISSION_INTEL_DB_PORT == 5506
        assert cfg.PERMISSION_INTEL_DB_USER == "erebus_pi_user"
        assert cfg.PERMISSION_INTEL_DB_PASSWORD == "erebus_pi_pw"
        """
        % (str(repo_root), str(src_root))
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
