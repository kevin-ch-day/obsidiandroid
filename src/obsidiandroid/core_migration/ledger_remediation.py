"""Receipted repair helpers for a partial Core migration ledger state.

These helpers verify physical DDL against reviewed migration bytes and prepare
or apply a single ledger INSERT.  They never re-run DDL.
"""

from __future__ import annotations

from hashlib import sha256
import json
import re
from pathlib import Path
from typing import Any


FAILED_PRODUCTION_RECEIPT_ID = "39b809e3ba7604f527a7f70e4ce988a63a93ed1ff69916b29e202f1727fb2ab5"
PRE_MIGRATION_BACKUP_SHA256 = "6fe86e7c08f63a7250e7224dcabbb417b92a45f019348d06186840b5df01f6e5"
MIGRATION_0004_VERSION = "0004"
MIGRATION_0004_NAME = "core_label_and_confusion_contracts"
MIGRATION_0004_CHECKSUM = "39d8ebfa55f9a4113ac2469b184504ff750cb7548f3a735df04d4f029e381942"
REMEDIATION_EXECUTOR_ID = "obsidiandroid-core-results-ledger-remediator"
PARTIAL_0004_TABLES = (
    "core_label_contract",
    "core_label_assignment",
    "core_confusion_cell",
)
EXPECTED_FIXTURE_COUNTS = {
    "core_profile": 1,
    "core_source_snapshot": 1,
    "core_run": 1,
    "core_run_sample": 9716,
    "core_artifact": 57,
    "core_quality_finding": 0,
}


class CoreLedgerRemediationError(RuntimeError):
    """Raised when a partial-migration ledger repair is unsafe."""


def load_failed_receipt(path: Path) -> dict[str, Any]:
    """Load and validate the immutable failed production migration receipt."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("receipt_id") != FAILED_PRODUCTION_RECEIPT_ID:
        raise CoreLedgerRemediationError("Failed receipt ID does not match the production incident authority")
    if payload.get("status") != "failed":
        raise CoreLedgerRemediationError("Failed receipt status must remain 'failed'")
    if payload.get("error_type") != "IntegrityError":
        raise CoreLedgerRemediationError("Failed receipt error_type must remain IntegrityError")
    if payload.get("applied") != ["0003"]:
        raise CoreLedgerRemediationError("Failed receipt applied set must be exactly ['0003']")
    return payload


def verify_backup_sha256(backup_path: Path, expected: str = PRE_MIGRATION_BACKUP_SHA256) -> str:
    """Return the backup digest after confirming it matches the incident authority."""
    digest = sha256(backup_path.read_bytes()).hexdigest()
    if digest != expected:
        raise CoreLedgerRemediationError("Pre-migration backup SHA-256 does not match the incident authority")
    return digest


def parse_expected_create_bodies(sql_text: str) -> dict[str, str]:
    """Extract CREATE TABLE bodies from reviewed 0004 SQL."""
    bodies: dict[str, str] = {}
    for table in PARTIAL_0004_TABLES:
        match = re.search(
            rf"CREATE TABLE {table} \((.*?)\n\) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
            sql_text,
            flags=re.S,
        )
        if not match:
            raise CoreLedgerRemediationError(f"Reviewed 0004 SQL is missing CREATE TABLE {table}")
        bodies[table] = match.group(1)
    return bodies


def _normalize_check_clause(clause: str) -> str:
    compact = re.sub(r"\s+", " ", clause).strip().lower()
    compact = compact.replace("`", "")
    return compact


def _parse_sql_column(line: str) -> tuple[str, str, str | None, str | None, bool]:
    nullable = "NOT NULL" not in line
    working = line
    for token in (" NOT NULL", " NULL"):
        working = working.replace(token, "")
    charset = None
    collation = None
    match = re.search(r"CHARACTER SET (\w+)", working)
    if match:
        charset = match.group(1)
        working = working.replace(match.group(0), "")
    match = re.search(r"COLLATE (\w+)", working)
    if match:
        collation = match.group(1)
        working = working.replace(match.group(0), "")
    name, type_text = working.split(" ", 1)
    return name, _canonical_type(type_text), charset, collation, nullable


def expected_table_digest_from_sql(table: str, body: str) -> dict[str, Any]:
    """Return a comparable contract summary for one CREATE TABLE body."""
    columns: list[tuple[str, str, str | None, str | None, bool]] = []
    primary_key: tuple[str, ...] = ()
    unique_keys: list[tuple[str, tuple[str, ...]]] = []
    foreign_keys: list[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = []
    checks: list[tuple[str, str]] = []
    for raw in body.splitlines():
        line = raw.strip().rstrip(",")
        if not line:
            continue
        if line.startswith("PRIMARY KEY"):
            cols = tuple(part.strip() for part in re.search(r"\((.*)\)", line).group(1).split(","))
            primary_key = cols
            continue
        if line.startswith("UNIQUE KEY"):
            match = re.match(r"UNIQUE KEY (\w+) \((.*)\)", line)
            unique_keys.append((match.group(1), tuple(part.strip() for part in match.group(2).split(","))))
            continue
        if line.startswith("CONSTRAINT ") and "FOREIGN KEY" in line:
            match = re.match(
                r"CONSTRAINT (\w+) FOREIGN KEY \((.*)\) REFERENCES (\w+) \((.*)\)",
                line,
            )
            foreign_keys.append(
                (
                    match.group(1),
                    tuple(part.strip() for part in match.group(2).split(",")),
                    match.group(3),
                    tuple(part.strip() for part in match.group(4).split(",")),
                )
            )
            continue
        if line.startswith("CONSTRAINT ") and "CHECK" in line:
            match = re.match(r"CONSTRAINT (\w+) CHECK \((.*)\)", line)
            checks.append((match.group(1), _normalize_check_clause(match.group(2))))
            continue
        columns.append(_parse_sql_column(line))
    return {
        "table": table,
        "engine": "InnoDB",
        "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",
        "columns": columns,
        "primary_key": primary_key,
        "unique_keys": sorted(unique_keys),
        "foreign_keys": sorted(foreign_keys),
        "checks": sorted(checks),
    }


def live_table_digest(cursor: Any, schema: str, table: str) -> dict[str, Any]:
    """Collect a comparable contract summary from information_schema."""
    cursor.execute(
        "SELECT ENGINE, TABLE_COLLATION FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
        (schema, table),
    )
    engine_row = cursor.fetchone()
    if not engine_row:
        raise CoreLedgerRemediationError(f"Required table is missing: {table}")
    engine, collation = str(engine_row[0]), str(engine_row[1])
    cursor.execute(
        "SELECT COLUMN_NAME, COLUMN_TYPE, CHARACTER_SET_NAME, COLLATION_NAME, IS_NULLABLE "
        "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
        "ORDER BY ORDINAL_POSITION",
        (schema, table),
    )
    columns = [
        (
            str(name),
            _canonical_type(str(column_type)),
            str(charset) if charset else None,
            str(col_collation) if col_collation else None,
            nullable == "YES",
        )
        for name, column_type, charset, col_collation, nullable in cursor.fetchall()
    ]

    cursor.execute(
        "SELECT CONSTRAINT_NAME, COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND CONSTRAINT_NAME='PRIMARY' "
        "ORDER BY ORDINAL_POSITION",
        (schema, table),
    )
    primary_key = tuple(str(row[1]) for row in cursor.fetchall())

    cursor.execute(
        "SELECT tc.CONSTRAINT_NAME, kcu.COLUMN_NAME "
        "FROM information_schema.TABLE_CONSTRAINTS tc "
        "JOIN information_schema.KEY_COLUMN_USAGE kcu "
        "  ON tc.CONSTRAINT_SCHEMA=kcu.CONSTRAINT_SCHEMA "
        " AND tc.CONSTRAINT_NAME=kcu.CONSTRAINT_NAME "
        " AND tc.TABLE_NAME=kcu.TABLE_NAME "
        "WHERE tc.TABLE_SCHEMA=%s AND tc.TABLE_NAME=%s AND tc.CONSTRAINT_TYPE='UNIQUE' "
        "ORDER BY tc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION",
        (schema, table),
    )
    unique_map: dict[str, list[str]] = {}
    for constraint_name, column_name in cursor.fetchall():
        unique_map.setdefault(str(constraint_name), []).append(str(column_name))
    unique_keys = sorted((name, tuple(cols)) for name, cols in unique_map.items())

    cursor.execute(
        "SELECT tc.CONSTRAINT_NAME, kcu.COLUMN_NAME, kcu.REFERENCED_TABLE_NAME, kcu.REFERENCED_COLUMN_NAME "
        "FROM information_schema.TABLE_CONSTRAINTS tc "
        "JOIN information_schema.KEY_COLUMN_USAGE kcu "
        "  ON tc.CONSTRAINT_SCHEMA=kcu.CONSTRAINT_SCHEMA "
        " AND tc.CONSTRAINT_NAME=kcu.CONSTRAINT_NAME "
        " AND tc.TABLE_NAME=kcu.TABLE_NAME "
        "WHERE tc.TABLE_SCHEMA=%s AND tc.TABLE_NAME=%s AND tc.CONSTRAINT_TYPE='FOREIGN KEY' "
        "ORDER BY tc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION",
        (schema, table),
    )
    fk_map: dict[str, list[tuple[str, str, str]]] = {}
    for constraint_name, column_name, referenced_table, referenced_column in cursor.fetchall():
        fk_map.setdefault(str(constraint_name), []).append(
            (str(column_name), str(referenced_table), str(referenced_column))
        )
    foreign_keys = []
    for name, parts in sorted(fk_map.items()):
        foreign_keys.append(
            (
                name,
                tuple(part[0] for part in parts),
                parts[0][1],
                tuple(part[2] for part in parts),
            )
        )

    cursor.execute(
        "SELECT CONSTRAINT_NAME, CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA=%s AND CONSTRAINT_NAME IN ("
        "  SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
        "  WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND CONSTRAINT_TYPE='CHECK'"
        ") ORDER BY CONSTRAINT_NAME",
        (schema, schema, table),
    )
    checks = sorted((str(name), _normalize_check_clause(str(clause))) for name, clause in cursor.fetchall())

    return {
        "table": table,
        "engine": engine,
        "charset": "utf8mb4" if collation.startswith("utf8mb4") else collation.split("_")[0],
        "collation": collation,
        "columns": columns,
        "primary_key": primary_key,
        "unique_keys": unique_keys,
        "foreign_keys": foreign_keys,
        "checks": checks,
    }


def _canonical_type(definition: str) -> str:
    text = definition.lower().strip()
    text = text.replace("int(10) unsigned", "int unsigned")
    text = text.replace("bigint(20) unsigned", "bigint unsigned")
    text = re.sub(r"\s+", " ", text)
    return text


def compare_table_digests(expected: dict[str, Any], live: dict[str, Any]) -> list[str]:
    """Return human-readable mismatches; empty means an acceptable match."""
    mismatches: list[str] = []
    for key in ("table", "engine", "charset", "collation", "primary_key", "unique_keys", "foreign_keys", "checks"):
        if expected[key] != live[key]:
            mismatches.append(f"{key}: expected {expected[key]!r} live {live[key]!r}")
    if len(expected["columns"]) != len(live["columns"]):
        mismatches.append(
            f"column_count: expected {len(expected['columns'])} live {len(live['columns'])}"
        )
        return mismatches
    for exp, got in zip(expected["columns"], live["columns"], strict=True):
        exp_name, exp_type, exp_charset, exp_collation, exp_null = exp
        live_name, live_type, live_charset, live_collation, live_null = got
        if exp_name != live_name or exp_type != live_type or exp_null != live_null:
            mismatches.append(f"column {exp_name}: expected {exp} live {got}")
            continue
        if exp_charset and (exp_charset != live_charset or exp_collation != live_collation):
            mismatches.append(
                f"column {exp_name} charset/collation: expected {exp_charset}/{exp_collation} "
                f"live {live_charset}/{live_collation}"
            )
    return mismatches


def physical_schema_verification_hash(digests: dict[str, dict[str, Any]]) -> str:
    """Hash the verified live contract in a stable, credential-free form."""
    payload = {table: digests[table] for table in sorted(digests)}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_remediation_notes(*, failed_receipt_id: str, backup_sha256: str, verification_hash: str) -> str:
    """Return the exact ledger notes string for the repair INSERT."""
    return (
        "ledger remediation for partial 0004 DDL; "
        f"failed_receipt_id={failed_receipt_id}; "
        f"backup_sha256={backup_sha256}; "
        f"physical_schema_verification_hash={verification_hash}; "
        "ddl_not_rerun=true"
    )


def build_ledger_row(
    *,
    migration_checksum: str,
    application_commit: str | None,
    mariadb_version: str,
    receipt_id: str,
    notes: str,
    execution_duration_ms: int = 0,
) -> dict[str, Any]:
    """Return the credential-free ledger row that remediation will insert."""
    return {
        "migration_version": MIGRATION_0004_VERSION,
        "migration_name": MIGRATION_0004_NAME,
        "migration_checksum": migration_checksum,
        "application_commit": application_commit,
        "executor_id": REMEDIATION_EXECUTOR_ID,
        "mariadb_version": mariadb_version,
        "execution_duration_ms": execution_duration_ms,
        "receipt_id": receipt_id,
        "execution_status": "applied",
        "notes": notes,
    }
