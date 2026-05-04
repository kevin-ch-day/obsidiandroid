"""Database layer tests: engine smoke, schema map, split Erebus + Permission Intel config."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

from mysql.connector import Error as MySQLError

from database import db_engine, schema_map
from database.db_config import DB_NAME, PERMISSION_INTEL_DB_NAME
from database.db_permission_analysis_queries import (
    fetch_android_banking_trojans_with_permissions,
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
    script = textwrap.dedent(
        """
        import os
        import sys
        sys.path.insert(0, %r)
        os.environ["OBSIDIAN_DB_NAME"] = "primary_from_env"
        os.environ["OBSIDIAN_PERMISSION_INTEL_DB_NAME"] = "pi_from_env"
        import database.db_config as cfg
        assert cfg.DB_NAME == "primary_from_env"
        assert cfg.PERMISSION_INTEL_DB_NAME == "pi_from_env"
        """
        % str(repo_root)
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
