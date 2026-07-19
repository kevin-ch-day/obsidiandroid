"""Fail-closed unit tests for the isolated ObsidianDroid core connection."""

from __future__ import annotations

import pytest

from obsidiandroid.database import db_engine


class _Cursor:
    def __init__(self, database: str) -> None:
        self.database = database
        self.executed: list[str] = []

    def execute(self, query: str, _params=None) -> None:
        self.executed.append(query)

    def fetchone(self):
        if self.executed and self.executed[-1] == "SELECT DATABASE()":
            return (self.database,)
        return (self.database, "+00:00")

    def close(self) -> None:
        return None


class _Connection:
    def __init__(self, database: str) -> None:
        self.database = database
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> _Cursor:
        return _Cursor(self.database)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def is_connected(self) -> bool:
        return not self.closed

    def close(self) -> None:
        self.closed = True


def _configure_core(monkeypatch, *, name: str = "obsidiandroid_core_prod") -> None:
    monkeypatch.setattr(db_engine, "CORE_DB_HOST", "localhost")
    monkeypatch.setattr(db_engine, "CORE_DB_USER", "core_writer")
    monkeypatch.setattr(db_engine, "CORE_DB_PASSWORD", "secret")
    monkeypatch.setattr(db_engine, "CORE_DB_NAME", name)


def test_missing_core_configuration_never_falls_back_to_primary(monkeypatch) -> None:
    monkeypatch.setattr(db_engine, "CORE_DB_HOST", "")
    monkeypatch.setattr(db_engine, "CORE_DB_USER", "")
    monkeypatch.setattr(db_engine, "CORE_DB_PASSWORD", "")
    primary_calls = {"count": 0}

    def primary_should_not_run():
        primary_calls["count"] += 1
        raise AssertionError("primary connection must not be used")

    monkeypatch.setattr(db_engine, "_get_connection", primary_should_not_run)

    with pytest.raises(db_engine.CoreDatabaseConfigurationError, match="incomplete"):
        with db_engine.core_database_connection():
            pass
    assert primary_calls["count"] == 0


@pytest.mark.parametrize(
    "forbidden",
    ["erebus_threat_intel_prod", "EREBUS_THREAT_INTEL_PROD", "android_permission_intel", "scytaledroid_core_prod"],
)
def test_forbidden_core_targets_fail_before_connect(monkeypatch, forbidden: str) -> None:
    _configure_core(monkeypatch, name=forbidden)
    calls = {"count": 0}

    def should_not_connect(*_args, **_kwargs):
        calls["count"] += 1
        raise AssertionError("unsafe core target must fail before connection")

    monkeypatch.setattr(db_engine, "_connect_with_localhost_fallback", should_not_connect)

    with pytest.raises(db_engine.CoreDatabaseConfigurationError, match="forbidden"):
        with db_engine.core_database_connection():
            pass
    assert calls["count"] == 0


def test_schema_mismatch_rolls_back_and_never_claims_health(monkeypatch) -> None:
    _configure_core(monkeypatch)
    conn = _Connection("erebus_threat_intel_prod")
    monkeypatch.setattr(db_engine, "_get_core_connection", lambda: conn)

    with pytest.raises(db_engine.CoreDatabaseConfigurationError, match="schema mismatch"):
        with db_engine.core_database_connection():
            pass

    assert conn.rolled_back is True
    assert conn.committed is False
    assert db_engine.core_database_health()["ok"] is False


def test_verified_core_connection_sets_utc_and_executes_without_primary(monkeypatch) -> None:
    _configure_core(monkeypatch)
    conn = _Connection("obsidiandroid_core_prod")
    monkeypatch.setattr(db_engine, "_get_core_connection", lambda: conn)

    with db_engine.core_database_connection() as connected:
        assert connected is conn

    assert conn.committed is True
    assert conn.rolled_back is False
    assert conn.closed is True


@pytest.mark.parametrize("statement", ["INSERT INTO core_run VALUES (1)", "DELETE FROM core_run", "CREATE TABLE x (id INT)"])
def test_core_query_helper_blocks_phase1_writes_before_connect(monkeypatch, statement: str) -> None:
    calls = {"count": 0}

    def should_not_connect():
        calls["count"] += 1
        raise AssertionError("write SQL must be rejected before opening a Core connection")

    monkeypatch.setattr(db_engine, "_get_core_connection", should_not_connect)

    with pytest.raises(db_engine.CoreDatabaseWriteBlockedError, match="blocked in Phase 1"):
        db_engine.execute_core_query(statement)
    assert calls["count"] == 0


def test_core_query_helper_blocks_multi_statement_sql_before_connect(monkeypatch) -> None:
    monkeypatch.setattr(
        db_engine,
        "_get_core_connection",
        lambda: (_ for _ in ()).throw(AssertionError("must not connect")),
    )

    with pytest.raises(db_engine.CoreDatabaseWriteBlockedError, match="multi-statement"):
        db_engine.execute_core_query("SELECT 1; DELETE FROM core_run")


def test_core_query_helper_permits_single_read_only_statement(monkeypatch) -> None:
    _configure_core(monkeypatch)
    conn = _Connection("obsidiandroid_core_prod")
    monkeypatch.setattr(db_engine, "_get_core_connection", lambda: conn)

    assert db_engine.execute_core_query("SELECT 1") is None
    assert conn.committed is True


def test_core_persistence_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(db_engine, "CORE_PERSISTENCE_ENABLED", False)
    assert db_engine.core_persistence_preflight() == {
        "ready": False,
        "status": "disabled",
        "reason": "feature_flag_disabled",
    }


def test_enabled_core_persistence_blocks_when_schema_ledger_missing(monkeypatch) -> None:
    monkeypatch.setattr(db_engine, "CORE_PERSISTENCE_ENABLED", True)
    monkeypatch.setattr(db_engine, "core_database_health", lambda: {"ok": True})
    monkeypatch.setattr(db_engine, "execute_core_query", lambda *_args, **_kwargs: [(0,)])

    result = db_engine.core_persistence_preflight()
    assert result["ready"] is False
    assert result["reason"] == "core_schema_migration_missing"


def test_enabled_core_persistence_requires_applied_foundation_ledger_entry(monkeypatch) -> None:
    monkeypatch.setattr(db_engine, "CORE_PERSISTENCE_ENABLED", True)
    monkeypatch.setattr(db_engine, "core_database_health", lambda: {"ok": True})

    def query_rows(query, **_kwargs):
        if "information_schema.TABLES" in query:
            return [(1,)]
        return [(0,)]

    monkeypatch.setattr(db_engine, "execute_core_query", query_rows)

    result = db_engine.core_persistence_preflight()
    assert result["ready"] is False
    assert result["reason"] == "core_schema_migration_not_applied"


def test_core_health_redacts_unexpected_connector_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        db_engine,
        "_get_core_connection",
        lambda: (_ for _ in ()).throw(RuntimeError("password=do-not-expose host=db.internal")),
    )

    health = db_engine.core_database_health()
    assert health["ok"] is False
    assert health["error"] == "Core database connection failed; no fallback to Erebus is permitted"
    assert "password" not in str(health["error"]).lower()
    assert "db.internal" not in str(health["error"])
