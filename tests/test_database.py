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
    db_engine.test_connection(verbose=False)


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


def test_check_split_database_health_structure(monkeypatch) -> None:
    """Health report includes expected keys (connectivity mocked)."""
    monkeypatch.setattr(
        db_engine.mysql.connector,
        "connect",
        MagicMock(side_effect=MySQLError("no db")),
    )
    report = db_engine.check_split_database_health()
    assert set(report.keys()) == {
        "primary_ok",
        "permission_intel_ok",
        "permission_obs_sample_in_pi",
    }
    assert report["primary_ok"] is False
    assert report["permission_intel_ok"] is False
    assert report["permission_obs_sample_in_pi"] is False


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
