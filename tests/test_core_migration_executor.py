"""Offline tests for the Core-only numbered migration executor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from obsidiandroid.core_migration.executor import (
    CoreMigrationError,
    _migration_receipt_id,
    apply_migrations,
    discover_migrations,
    validate_target_name,
)


def _write(directory: Path, name: str, text: str = "SELECT 1;") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


def test_discover_migrations_is_ordered_and_hashed(tmp_path: Path) -> None:
    _write(tmp_path, "0001_first.sql")
    _write(tmp_path, "0002_second.sql")
    found = discover_migrations(tmp_path)
    assert [item.version for item in found] == ["0001", "0002"]
    assert all(len(item.checksum) == 64 for item in found)


def test_discover_migrations_rejects_gap_and_invalid_name(tmp_path: Path) -> None:
    _write(tmp_path, "0001_first.sql")
    _write(tmp_path, "0003_third.sql")
    with pytest.raises(CoreMigrationError, match="contiguous"):
        discover_migrations(tmp_path)
    (tmp_path / "not-a-migration.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(CoreMigrationError, match="Invalid"):
        discover_migrations(tmp_path)


@pytest.mark.parametrize("name", ["erebus_threat_intel_prod", "android_permission_intel", "obsidiandroid_core_prod", "phase2a_restore"])
def test_protected_schema_is_rejected(name: str) -> None:
    with pytest.raises(CoreMigrationError):
        validate_target_name(name)


def test_dry_run_never_needs_connection_and_writes_receipt(tmp_path: Path) -> None:
    _write(tmp_path / "migrations", "0001_first.sql")
    receipt = tmp_path / "receipt.json"
    result = apply_migrations(
        target_database="od_core_phase2b_validate_20260719T120000Z",
        migrations_dir=tmp_path / "migrations",
        dry_run=True,
        receipt_path=receipt,
    )
    assert result["status"] == "planned"
    assert receipt.exists()
    assert result["invocation_id"] == result["receipt_id"]
    assert set(result["migration_receipt_ids"]) == {"0001"}


def test_migration_receipt_ids_are_unique_per_version() -> None:
    invocation = "a" * 64
    first = _migration_receipt_id(invocation_id=invocation, version="0003", checksum="b" * 64)
    second = _migration_receipt_id(invocation_id=invocation, version="0004", checksum="c" * 64)
    assert first != second
    assert len(first) == 64
    assert first == _migration_receipt_id(invocation_id=invocation, version="0003", checksum="b" * 64)


class _FakeCursor:
    """Minimal cursor that records ledger inserts and simulates applied history."""

    def __init__(self, ledger: dict[str, tuple[str, str]], target: str) -> None:
        self.ledger = ledger
        self.target = target
        self.receipt_ids: list[str] = []
        self.statements: list[tuple[str, tuple[Any, ...] | None]] = []
        self._last: Any = None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.statements.append((sql, params))
        text = " ".join(sql.split())
        if text.startswith("SELECT DATABASE()"):
            self._last = (self.target,)
        elif text.startswith("SELECT migration_version"):
            self._last = [(version, checksum, status) for version, (checksum, status) in self.ledger.items()]
        elif text.startswith("SELECT VERSION()"):
            self._last = ("10.11.18-MariaDB",)
        elif text.startswith("INSERT INTO core_schema_migration"):
            assert params is not None
            version = str(params[0])
            checksum = str(params[2])
            if len(params) >= 8:
                receipt_id = str(params[7])
                if receipt_id in self.receipt_ids:
                    raise RuntimeError(f"Duplicate entry '{receipt_id}' for key 'uq_core_schema_migration_receipt'")
                self.receipt_ids.append(receipt_id)
            self.ledger[version] = (checksum, "applied")
            self._last = None
        else:
            self._last = None

    def fetchone(self) -> Any:
        if isinstance(self._last, list):
            return None
        return self._last

    def fetchall(self) -> list[Any]:
        if isinstance(self._last, list):
            return self._last
        return []

    def close(self) -> None:
        return None


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.commits = 0

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_multi_migration_run_uses_distinct_ledger_receipt_ids(tmp_path: Path) -> None:
    """Regression for the production 0003/0004 IntegrityError on shared receipt_id."""
    migrations = tmp_path / "migrations"
    _write(migrations, "0001_a.sql", "SELECT 1;\n")
    _write(migrations, "0002_b.sql", "SELECT 1;\n")
    _write(migrations, "0003_c.sql", "CREATE TABLE core_t3 (id INT PRIMARY KEY);\n")
    _write(migrations, "0004_d.sql", "CREATE TABLE core_t4 (id INT PRIMARY KEY);\n")
    discovered = discover_migrations(migrations)
    target = "od_core_phase2b_validate_20260720T120000Z"
    cursor = _FakeCursor(
        ledger={
            "0001": (discovered[0].checksum, "applied"),
            "0002": (discovered[1].checksum, "applied"),
        },
        target=target,
    )
    # Seed an already-ledgered receipt so a reused invocation id would collide.
    cursor.receipt_ids.append("prior-unique-receipt")
    connection = _FakeConnection(cursor)

    receipt_path = tmp_path / "receipt.json"
    result = apply_migrations(
        target_database=target,
        migrations_dir=migrations,
        connection_factory=lambda _database: connection,
        dry_run=False,
        receipt_path=receipt_path,
        executor_id="unit-test-migrator",
    )

    assert result["status"] == "applied"
    assert result["skipped"] == ["0001", "0002"]
    assert result["applied"] == ["0003", "0004"]
    assert connection.commits == 2
    assert len(cursor.receipt_ids) == 3  # prior + 0003 + 0004
    assert cursor.receipt_ids[-2] != cursor.receipt_ids[-1]
    assert result["migration_receipt_ids"]["0003"] == cursor.receipt_ids[-2]
    assert result["migration_receipt_ids"]["0004"] == cursor.receipt_ids[-1]
    assert result["migration_receipt_ids"]["0003"] != result["migration_receipt_ids"]["0004"]
    assert set(result["migration_receipt_ids"]) == {"0001", "0002", "0003", "0004"}
