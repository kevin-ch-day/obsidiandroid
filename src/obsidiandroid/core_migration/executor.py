"""Dedicated, fail-closed executor for numbered ObsidianDroid Core migrations.

Normal application persistence remains disabled.  This module is deliberately
unaware of the primary and Permission Intel connection helpers: callers must
provide a Core-only connection factory and an explicitly approved target.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from time import perf_counter
from typing import Any, Callable, Iterable


class CoreMigrationError(RuntimeError):
    """Raised when a Core migration target, history, or execution is unsafe."""


_MIGRATION_NAME = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")
_DISPOSABLE_TARGET = re.compile(r"^od_core_phase2b_validate_\d{8}T\d{6}Z(?:_[a-z0-9]+)?$")
_FORBIDDEN_TARGETS = frozenset(
    {
        "erebus_threat_intel_prod",
        "android_permission_intel",
        "obsidiandroid_core_prod",
        "scytaledroid_core_prod",
    }
)


@dataclass(frozen=True)
class MigrationFile:
    """One content-addressed numbered SQL migration."""

    version: str
    name: str
    path: Path
    checksum: str


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def validate_target_name(target_database: str, *, allow_production: bool = False) -> str:
    """Accept only Phase 2B disposable schemas unless production is separately allowed."""
    target = str(target_database or "").strip()
    lowered = target.casefold()
    if lowered in _FORBIDDEN_TARGETS:
        if lowered == "obsidiandroid_core_prod" and allow_production:
            return target
        raise CoreMigrationError(f"Protected or source schema is not an approved target: {target!r}")
    if not _DISPOSABLE_TARGET.fullmatch(target):
        raise CoreMigrationError(
            "Core migration target must be an explicit Phase 2B disposable schema; "
            f"got {target!r}"
        )
    return target


def discover_migrations(migrations_dir: Path) -> tuple[MigrationFile, ...]:
    """Return contiguous numbered migrations with content hashes, or fail closed."""
    paths = sorted(Path(migrations_dir).glob("*.sql"))
    discovered: list[MigrationFile] = []
    versions: set[str] = set()
    for path in paths:
        match = _MIGRATION_NAME.fullmatch(path.name)
        if not match:
            raise CoreMigrationError(f"Invalid Core migration filename: {path.name}")
        version = match.group("version")
        if version in versions:
            raise CoreMigrationError(f"Duplicate Core migration version: {version}")
        versions.add(version)
        discovered.append(
            MigrationFile(
                version=version,
                name=match.group("name"),
                path=path,
                checksum=sha256(path.read_bytes()).hexdigest(),
            )
        )
    if not discovered:
        raise CoreMigrationError("No Core migrations were discovered")
    expected = [f"{number:04d}" for number in range(1, len(discovered) + 1)]
    actual = [item.version for item in discovered]
    if actual != expected:
        raise CoreMigrationError(f"Core migration versions must be contiguous from 0001: {actual!r}")
    return tuple(discovered)


def split_sql_statements(sql: str) -> tuple[str, ...]:
    """Split the reviewed DDL without treating semicolons inside quoted strings as delimiters."""
    statements: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    escaped = False
    for character in sql:
        buffer.append(character)
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif character in ("'", '"', "`"):
            quote = character
        elif character == ";":
            statement = "".join(buffer[:-1]).strip()
            if statement:
                statements.append(statement)
            buffer = []
    remainder = "".join(buffer).strip()
    if remainder:
        raise CoreMigrationError("Migration SQL ends with an unterminated statement")
    return tuple(statements)


def _fetch_applied(cursor: Any) -> dict[str, tuple[str, str]]:
    """Return existing ledger records, accepting a fresh schema before 0001."""
    try:
        cursor.execute(
            "SELECT migration_version, migration_checksum, execution_status "
            "FROM core_schema_migration ORDER BY migration_version"
        )
        return {str(row[0]): (str(row[1]), str(row[2])) for row in cursor.fetchall()}
    except Exception as exc:
        message = str(exc).casefold()
        if "core_schema_migration" in message and ("doesn't exist" in message or "does not exist" in message):
            return {}
        raise CoreMigrationError("Unable to read Core migration ledger") from exc


def _execute_script(cursor: Any, migration: MigrationFile) -> None:
    for statement in split_sql_statements(migration.path.read_text(encoding="utf-8")):
        # Comments are acceptable in a statement; MariaDB parses them with DDL.
        cursor.execute(statement)


def _write_receipt(receipt: dict[str, Any], receipt_path: Path | None) -> None:
    if receipt_path is None:
        return
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def apply_migrations(
    *,
    target_database: str,
    migrations_dir: Path,
    connection_factory: Callable[[str], Any] | None = None,
    application_commit: str | None = None,
    executor_id: str = "obsidiandroid-core-migrator",
    dry_run: bool = True,
    allow_production: bool = False,
    receipt_path: Path | None = None,
) -> dict[str, Any]:
    """Plan or apply migrations through an injected Core-only connection factory.

    Each migration is ledgered only after all its statements complete.  MariaDB
    DDL may auto-commit, so a failed DDL migration is reported in the receipt
    and never claimed as applied; its schema effects require operator review.
    """
    target = validate_target_name(target_database, allow_production=allow_production)
    migrations = discover_migrations(Path(migrations_dir))
    receipt: dict[str, Any] = {
        "receipt_version": "core-migration-receipt-v1",
        "receipt_id": sha256(f"{target}|{_utc_now()}|{executor_id}".encode()).hexdigest(),
        "target_database": target,
        "dry_run": bool(dry_run),
        "executor_id": executor_id,
        "application_commit": application_commit,
        "started_at_utc": _utc_now(),
        "migrations": [asdict(item) | {"path": str(item.path)} for item in migrations],
        "applied": [],
        "skipped": [],
        "status": "planned" if dry_run else "running",
    }
    if dry_run:
        receipt["completed_at_utc"] = _utc_now()
        _write_receipt(receipt, receipt_path)
        return receipt
    if connection_factory is None:
        raise CoreMigrationError("An injected dedicated Core connection factory is required for execution")
    connection = None
    cursor = None
    try:
        connection = connection_factory(target)
        cursor = connection.cursor()
        cursor.execute("SET time_zone = '+00:00'")
        cursor.execute("SELECT DATABASE()")
        row = cursor.fetchone()
        if str(row[0] if row else "") != target:
            raise CoreMigrationError("Dedicated Core connection did not select the approved target schema")
        applied = _fetch_applied(cursor)
        for migration in migrations:
            existing = applied.get(migration.version)
            if existing:
                checksum, status = existing
                if checksum != migration.checksum:
                    raise CoreMigrationError(f"Checksum mismatch for already ledgered migration {migration.version}")
                if status != "applied":
                    raise CoreMigrationError(f"Migration {migration.version} has unsafe ledger status {status!r}")
                receipt["skipped"].append(migration.version)
                continue
            started = perf_counter()
            _execute_script(cursor, migration)
            duration_ms = round((perf_counter() - started) * 1000)
            if migration.version == "0001":
                # The preserved foundation necessarily has only its original
                # ledger columns.  The local receipt supplies the missing
                # executor/version timing facts for this one historical row.
                cursor.execute(
                    "INSERT INTO core_schema_migration "
                    "(migration_version, migration_name, migration_checksum, applied_at_utc, "
                    "application_commit, execution_status, notes) "
                    "VALUES (%s, %s, %s, UTC_TIMESTAMP(6), %s, 'applied', %s)",
                    (migration.version, migration.name, migration.checksum, application_commit,
                     f"executor={executor_id}; duration_ms={duration_ms}; receipt={receipt['receipt_id']}"),
                )
            else:
                cursor.execute("SELECT VERSION()")
                server_version = str(cursor.fetchone()[0])
                cursor.execute(
                    "INSERT INTO core_schema_migration "
                    "(migration_version, migration_name, migration_checksum, applied_at_utc, application_commit, "
                    "executor_id, mariadb_version, execution_duration_ms, receipt_id, execution_status, notes) "
                    "VALUES (%s,%s,%s,UTC_TIMESTAMP(6),%s,%s,%s,%s,%s,'applied',%s)",
                    (migration.version, migration.name, migration.checksum, application_commit, executor_id,
                     server_version, duration_ms, receipt["receipt_id"], "applied by dedicated Core executor"),
                )
            connection.commit()
            receipt["applied"].append(migration.version)
        receipt["status"] = "applied"
    except Exception as exc:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        receipt["status"] = "failed"
        receipt["error_type"] = type(exc).__name__
        receipt["error"] = "Core migration failed; inspect the local receipt and target schema without credentials."
        raise
    finally:
        receipt["completed_at_utc"] = _utc_now()
        _write_receipt(receipt, receipt_path)
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()
    return receipt
