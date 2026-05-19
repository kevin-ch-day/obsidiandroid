"""Database layer tests: engine smoke, schema map, split Erebus + Permission Intel config."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

from mysql.connector import Error as MySQLError

from obsidiandroid.database import db_engine, schema_map
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


def test_test_connection_does_not_raise_unboundlocal_on_connect_failure(monkeypatch) -> None:
    """Connection smoke test should swallow connector errors without masking them."""

    def _raise(*_args, **_kwargs):
        raise MySQLError("boom")

    monkeypatch.setattr(db_engine.mysql.connector, "connect", _raise)
    assert db_engine.test_connection(verbose=False) is False


def test_schema_table_resolution():
    assert schema_map.table("vendor_engines") == "virustotal_vendor_engines"
    assert schema_map.table("vendor_verdicts") == "virustotal_sample_vendor_engine_verdicts"


def test_schema_column_resolution():
    assert schema_map.column("vendor_engines", "engine_name") == "vendor_key"
    assert schema_map.column("vendor_engines", "trusted_flag") == "is_trusted_vendor"
    assert schema_map.column("vendor_engines", "active_flag") == "is_engine_active"


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
    db_engine.execute_permission_query("SELECT 1", fetch=False)
    assert captured.get("database") == PERMISSION_INTEL_DB_NAME


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

    monkeypatch.setattr(
        db_engine,
        "get_table_columns",
        lambda _table: ["sample_id", "permission_string", "permission_string_norm"],
    )
    monkeypatch.setattr(
        "obsidiandroid.database.db_permission_analysis_queries._PERMISSION_OBS_NORM_AVAILABLE",
        None,
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

    monkeypatch.setattr(
        db_engine,
        "get_table_columns",
        lambda _table: ["sample_id", "permission_string"],
    )
    monkeypatch.setattr(
        "obsidiandroid.database.db_permission_analysis_queries._PERMISSION_OBS_NORM_AVAILABLE",
        None,
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
