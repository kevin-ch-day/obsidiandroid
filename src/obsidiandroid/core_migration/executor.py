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
_DISPOSABLE_TARGET = re.compile(
    r"^od_core_phase2(?:b_validate|c_rehearsal)_\d{8}T\d{6}Z(?:_[a-z0-9]+)?$"
)
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
    """Accept only named disposable Core schemas unless production is separately allowed.

    ``od_core_phase2c_rehearsal_*`` is deliberately distinct from the Phase
    2B synthetic-validation namespace.  It is the only non-production target
    class permitted for Phase 2C replay and rollback rehearsals.
    """
    target = str(target_database or "").strip()
    lowered = target.casefold()
    if lowered in _FORBIDDEN_TARGETS:
        if lowered == "obsidiandroid_core_prod" and allow_production:
            return target
        raise CoreMigrationError(f"Protected or source schema is not an approved target: {target!r}")
    if not _DISPOSABLE_TARGET.fullmatch(target):
        raise CoreMigrationError(
            "Core migration target must be an explicit Phase 2B validation or Phase 2C rehearsal schema; "
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
    """Split reviewed DDL on statement terminators outside quotes and comments.

    MariaDB accepts ``--`` line comments and ``/* ... */`` block comments in
    migration files.  Semicolons inside those comments must not become statement
    boundaries; that footgun previously forced operators to avoid ``;`` in
    comments entirely.
    """
    statements: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    escaped = False
    in_line_comment = False
    in_block_comment = False
    index = 0
    length = len(sql)
    while index < length:
        character = sql[index]
        nxt = sql[index + 1] if index + 1 < length else ""
        if in_line_comment:
            buffer.append(character)
            if character == "\n":
                in_line_comment = False
            index += 1
            continue
        if in_block_comment:
            buffer.append(character)
            if character == "*" and nxt == "/":
                buffer.append(nxt)
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue
        if quote:
            buffer.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue
        if character == "-" and nxt == "-":
            buffer.append(character)
            buffer.append(nxt)
            in_line_comment = True
            index += 2
            continue
        if character == "/" and nxt == "*":
            buffer.append(character)
            buffer.append(nxt)
            in_block_comment = True
            index += 2
            continue
        if character in ("'", '"', "`"):
            buffer.append(character)
            quote = character
            index += 1
            continue
        if character == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            index += 1
            continue
        buffer.append(character)
        index += 1
    remainder = "".join(buffer).strip()
    if remainder:
        raise CoreMigrationError("Migration SQL ends with an unterminated statement")
    return tuple(statements)


def _safe_db_error_fields(exc: BaseException) -> dict[str, Any]:
    """Capture credential-free connector metadata for migration receipts."""
    fields: dict[str, Any] = {"error_type": type(exc).__name__}
    errno = getattr(exc, "errno", None)
    sqlstate = getattr(exc, "sqlstate", None)
    if isinstance(errno, int):
        fields["error_errno"] = errno
    if isinstance(sqlstate, str) and sqlstate:
        fields["error_sqlstate"] = sqlstate
    return fields


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


def _migration_receipt_id(*, invocation_id: str, version: str, checksum: str) -> str:
    """Return a durable, unique receipt id for one migration version.

    The schema enforces ``UNIQUE (receipt_id)``.  One invocation may apply
    several migrations, so each version must receive a distinct id derived from
    the invocation identity plus the version and content hash.
    """
    return sha256(f"{invocation_id}|{version}|{checksum}".encode()).hexdigest()


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

    The external receipt identifies the whole invocation.  Each ledgered
    migration version receives its own ``receipt_id`` so multi-migration runs
    cannot collide with ``uq_core_schema_migration_receipt``.
    """
    target = validate_target_name(target_database, allow_production=allow_production)
    migrations = discover_migrations(Path(migrations_dir))
    invocation_id = sha256(f"{target}|{_utc_now()}|{executor_id}".encode()).hexdigest()
    planned_receipt_ids = {
        item.version: _migration_receipt_id(
            invocation_id=invocation_id, version=item.version, checksum=item.checksum
        )
        for item in migrations
    }
    receipt: dict[str, Any] = {
        "receipt_version": "core-migration-receipt-v1",
        # File-level correlation id for the whole apply_migrations() call.
        "receipt_id": invocation_id,
        "invocation_id": invocation_id,
        "migration_receipt_ids": planned_receipt_ids,
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
            migration_receipt = planned_receipt_ids[migration.version]
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
                     f"executor={executor_id}; duration_ms={duration_ms}; receipt={migration_receipt}"),
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
                     server_version, duration_ms, migration_receipt, "applied by dedicated Core executor"),
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
        receipt.update(_safe_db_error_fields(exc))
        receipt["error"] = "Core migration failed; inspect the local receipt and target schema without credentials."
        # MariaDB DDL may already have auto-committed before the ledger INSERT.
        receipt["partial_ddl_review_required"] = True
        raise
    finally:
        receipt["completed_at_utc"] = _utc_now()
        _write_receipt(receipt, receipt_path)
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()
    return receipt
