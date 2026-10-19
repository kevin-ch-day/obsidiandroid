"""Negative checks must never open a real connection, even on failure."""
import socket
import pytest
import mysql.connector
from mysql.connector import pooling
from mysql.connector.connection import MySQLConnection
from scripts.dev.pytest_database_guard import (
    OfflineDatabaseAccessError, live_access_allowed, _guard, _ALLOWED,
)


@pytest.mark.parametrize("option,marked,expected", [
    (False, False, False), (True, False, False),
    (False, True, False), (True, True, True),
])
def test_live_database_requires_both_opt_ins(option, marked, expected):
    assert live_access_allowed(option, marked) is expected


@pytest.mark.parametrize("connect", [
    mysql.connector.connect, pooling.connect,
    MySQLConnection.connect, pooling.MySQLConnectionPool.get_connection,
])
def test_database_entrypoints_block_before_connect(connect):
    with pytest.raises(OfflineDatabaseAccessError):
        connect()


def test_native_connector_is_blocked():
    if not mysql.connector.HAVE_CEXT:
        pytest.skip("Native connector unavailable")
    from mysql.connector.connection_cext import CMySQLConnection
    with pytest.raises(OfflineDatabaseAccessError):
        CMySQLConnection.connect()


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_socket_connections_are_blocked(method):
    with socket.socket() as client:
        with pytest.raises(OfflineDatabaseAccessError):
            getattr(client, method)(("127.0.0.1", 3306))


def test_allow_path_uses_a_fake_transport_only():
    calls = []
    guarded = _guard(lambda: calls.append("fake"))
    with pytest.raises(OfflineDatabaseAccessError):
        guarded()
    token = _ALLOWED.set(True)
    try:
        guarded()
    finally:
        _ALLOWED.reset(token)
    assert calls == ["fake"]
    with pytest.raises(OfflineDatabaseAccessError):
        guarded()


def test_real_readiness_connection_path_is_stopped(monkeypatch):
    from obsidiandroid.database import db_engine
    monkeypatch.setattr(db_engine, "_build_connect_kwargs", lambda: {})
    monkeypatch.setattr(db_engine, "DB_ENABLE_POOLING", False)
    with pytest.raises(OfflineDatabaseAccessError):
        db_engine.execute_query("SELECT 1", fetch=True)


def test_collection_is_guarded_before_test_fixtures(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys

    test_file = tmp_path / "test_collection_probe.py"
    test_file.write_text("import mysql.connector\nmysql.connector.connect()\n")
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(root), str(root / "src")]))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "scripts.dev.pytest_database_guard",
         "-o", "addopts=", "-q", str(test_file)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2
    assert "OfflineDatabaseAccessError" in result.stdout
