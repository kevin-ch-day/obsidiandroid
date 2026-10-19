"""Deny real database/network connections in pytest unless explicitly opted in.

Loaded by tests/conftest.py before test collection. Integration markers alone
do not authorize live access. This guards this Python process, not arbitrary
external executables launched by tests.
"""
from contextvars import ContextVar
from functools import wraps
import socket
import json
from pathlib import Path
import traceback

import pytest

_ATTEMPTS = []
_TEST_ID = ContextVar("pytest_connection_test_id", default="collection")
_ALLOWED = ContextVar("pytest_live_database_allowed", default=False)


class OfflineDatabaseAccessError(RuntimeError):
    """A test attempted a real connection without the explicit live opt-in."""


def live_access_allowed(option, marked):
    """Require both invocation approval and a per-test live database marker."""
    return option is True and marked is True


def _guard(original):
    @wraps(original)
    def guarded(*args, **kwargs):
        if not _ALLOWED.get():
            _ATTEMPTS.append({
                "test": _TEST_ID.get(),
                "entrypoint": getattr(original, "__module__", "socket") + "." + original.__qualname__,
                "stack": [
                    {"path": frame.filename, "line": frame.lineno, "function": frame.name}
                    for frame in traceback.extract_stack(limit=14)[:-1]
                ],
            })
            raise OfflineDatabaseAccessError(
                "Offline pytest blocked a real connection; use fixtures. "
                "Authorized database tests require --allow-live-database and @pytest.mark.live_database."
            )
        return original(*args, **kwargs)
    return guarded


def pytest_addoption(parser):
    parser.addoption(
        "--allow-live-database", action="store_true", default=False,
        help="Opt in to separately authorized live_database tests; never used by CI.",
    )
    parser.addoption("--offline-connection-report", default=None,
                     help="Write credential-free blocked-connection traces to this JSON path.")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live_database: explicitly authorized live database test; requires --allow-live-database"
    )
    patch = pytest.MonkeyPatch()
    config._offline_database_patch = patch
    import mysql.connector
    import mysql.connector.pooling
    from mysql.connector.connection import MySQLConnection
    targets = [
        (mysql.connector, "connect"), (mysql.connector.pooling, "connect"),
        (mysql.connector.pooling.MySQLConnectionPool, "get_connection"),
        (MySQLConnection, "connect"),
        (socket.socket, "connect"), (socket.socket, "connect_ex"),
    ]
    if mysql.connector.HAVE_CEXT:
        from mysql.connector.connection_cext import CMySQLConnection
        targets.append((CMySQLConnection, "connect"))
    for owner, name in targets:
        patch.setattr(owner, name, _guard(getattr(owner, name)))


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    test_token = _TEST_ID.set(item.nodeid)
    token = _ALLOWED.set(live_access_allowed(
        item.config.getoption("--allow-live-database"),
        item.get_closest_marker("live_database") is not None,
    ))
    try:
        yield
    finally:
        _ALLOWED.reset(token)
        _TEST_ID.reset(test_token)



def pytest_sessionfinish(session, exitstatus):
    path = session.config.getoption("--offline-connection-report")
    if path:
        Path(path).write_text(json.dumps({
            "exit_status": int(exitstatus), "blocked_attempts": _ATTEMPTS,
            "scope": "current pytest Python process; no credentials or SQL parameters recorded",
        }, indent=2) + "\n")


def pytest_unconfigure(config):
    patch = getattr(config, "_offline_database_patch", None)
    if patch is not None:
        patch.undo()
