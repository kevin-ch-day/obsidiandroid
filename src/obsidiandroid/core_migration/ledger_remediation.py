"""Receipted repair helpers for a partial Core migration ledger state.

These helpers verify physical DDL against reviewed migration bytes and prepare
or apply a single ledger INSERT.  They never re-run DDL.
"""

from __future__ import annotations

from datetime import UTC, datetime
from getpass import getuser
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable

from obsidiandroid.core_migration.authorization import mariadb_server_attestation
from obsidiandroid.core_migration.migration_checksums import (
    CORE_RESULT_TABLES_TEMPORARY,
    FAILED_PRODUCTION_RECEIPT_ID,
    MIGRATION_CHECKSUMS,
    PARTIAL_0004_TABLES,
    PHASE2C_FIXTURE_COUNTS,
    PHASE2C_FIXTURE_RUN_ID,
    PRE_MIGRATION_BACKUP_SHA256,
    PRODUCTION_CORE,
    REMEDIATION_EXECUTOR_ID,
    verify_repository_migration_checksums,
)
from obsidiandroid.core_migration.structural_digest import (
    compare_structural_digests,
    expected_structural_digest_from_sql,
    live_structural_digest,
    package_structural_digest,
    parse_expected_create_bodies,
)


RECEIPT_VERSION = "core-0004-ledger-remediation-v2"
STATUS_PLANNED = "planned"
STATUS_APPLYING = "applying"
STATUS_APPLIED_AND_VERIFIED = "applied_and_verified"
STATUS_COMMITTED_BUT_POSTCHECK_FAILED = "committed_but_postcheck_failed"
STATUS_FAILED_BEFORE_COMMIT = "failed_before_commit"

MIGRATION_0004_VERSION = "0004"
MIGRATION_0004_NAME = "core_label_and_confusion_contracts"
MIGRATION_0004_CHECKSUM = MIGRATION_CHECKSUMS["0004"]

# Compat aliases used by older imports/tests.
EXPECTED_FIXTURE_COUNTS = PHASE2C_FIXTURE_COUNTS


class CoreLedgerRemediationError(RuntimeError):
    """Raised when a partial-migration ledger repair is unsafe."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


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


def create_receipt_exclusive(path: Path, payload: dict[str, Any]) -> None:
    """Create a new receipt file; refuse if the path already exists."""
    if path.exists():
        raise CoreLedgerRemediationError(f"Refusing to overwrite an existing remediation receipt: {path}")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def replace_receipt_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Atomically replace an existing remediation receipt during state transitions."""
    if not path.exists():
        raise CoreLedgerRemediationError(f"Remediation receipt missing for state transition: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def write_emergency_receipt(directory: Path, payload: dict[str, Any]) -> Path:
    """Write a unique emergency receipt when post-commit finalization fails."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / f"0004_ledger_remediation_EMERGENCY_{stamp}.json"
    create_receipt_exclusive(path, payload)
    return path


def build_remediation_notes(*, failed_receipt_id: str, backup_sha256: str, verification_hash: str) -> str:
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


def collect_server_attestation(cursor: Any) -> dict[str, Any]:
    cursor.execute("SELECT @@hostname, @@port, @@server_id, @@version, @@version_comment")
    hostname, port, server_id, version, version_comment = cursor.fetchone()
    attestation = {
        "attestation_version": "mariadb-server-attestation-v1",
        "hostname": str(hostname),
        "port": int(port),
        "server_id": int(server_id),
        "version": str(version),
        "version_comment": str(version_comment),
    }
    attestation["sha256"] = mariadb_server_attestation(
        hostname=attestation["hostname"],
        port=attestation["port"],
        server_id=attestation["server_id"],
        version=attestation["version"],
        version_comment=attestation["version_comment"],
    )
    return attestation


def attest_remediation_target(
    cursor: Any,
    *,
    target_database: str,
    approved_current_user: str,
    approved_server_attestation_sha256: str | None,
) -> dict[str, Any]:
    """Verify DATABASE()/CURRENT_USER()/server attestation before any write."""
    cursor.execute("SELECT DATABASE(), CURRENT_USER(), VERSION()")
    database_name, current_user, version = cursor.fetchone()
    if str(database_name) != target_database:
        raise CoreLedgerRemediationError(
            f"DATABASE() mismatch: expected {target_database!r} got {database_name!r}"
        )
    if str(current_user) != approved_current_user:
        raise CoreLedgerRemediationError(
            f"CURRENT_USER() mismatch: expected {approved_current_user!r} got {current_user!r}"
        )
    attestation = collect_server_attestation(cursor)
    if approved_server_attestation_sha256 is not None:
        if attestation["sha256"] != approved_server_attestation_sha256:
            raise CoreLedgerRemediationError("MariaDB server attestation does not match the approved input")
    return {
        "database": str(database_name),
        "current_user": str(current_user),
        "mariadb_version": str(version),
        "server_attestation": attestation,
    }


def verify_ledger_partial_0004_preconditions(cursor: Any, *, schema: str) -> dict[str, Any]:
    cursor.execute(
        f"SELECT migration_version, migration_checksum, execution_status, receipt_id "
        f"FROM `{schema}`.core_schema_migration ORDER BY migration_version"
    )
    rows = [(str(v), str(c), str(s), None if r is None else str(r)) for v, c, s, r in cursor.fetchall()]
    unexpected_status = [row for row in rows if row[2] not in {"applied", "rolled_back"}]
    if unexpected_status:
        raise CoreLedgerRemediationError(f"Unexpected migration ledger status values: {unexpected_status}")
    applied = {version: checksum for version, checksum, status, _receipt in rows if status == "applied"}
    if set(applied) != {"0001", "0002", "0003"}:
        raise CoreLedgerRemediationError(
            f"Ledger must contain exactly applied 0001-0003 before repair; found {sorted(applied)}"
        )
    for version in ("0001", "0002", "0003"):
        if applied[version] != MIGRATION_CHECKSUMS[version]:
            raise CoreLedgerRemediationError(
                f"Ledger checksum mismatch for {version}: ledger={applied[version]} expected={MIGRATION_CHECKSUMS[version]}"
            )
    versions = {version for version, *_rest in rows}
    if "0004" in versions:
        raise CoreLedgerRemediationError("Refusing repair: 0004 is already present in the ledger")
    if "0005" in versions:
        raise CoreLedgerRemediationError("Refusing repair: 0005 is already present in the ledger")
    receipt_by_version = {version: receipt for version, _checksum, status, receipt in rows if status == "applied"}
    if receipt_by_version.get("0003") != FAILED_PRODUCTION_RECEIPT_ID and schema == PRODUCTION_CORE:
        raise CoreLedgerRemediationError("Ledger is missing the failed production receipt_id on 0003")
    return {"applied": applied, "rows": rows, "receipt_by_version": receipt_by_version}


def verify_fixture_identity(cursor: Any, *, schema: str) -> dict[str, Any]:
    cursor.execute(f"SELECT run_id FROM `{schema}`.core_run ORDER BY run_id")
    run_ids = [str(row[0]) for row in cursor.fetchall()]
    if run_ids != [PHASE2C_FIXTURE_RUN_ID]:
        # Disposable rehearsals may use synthetic runs; production must be exact.
        if schema == PRODUCTION_CORE:
            raise CoreLedgerRemediationError(
                f"Fixture run identity mismatch: expected {[PHASE2C_FIXTURE_RUN_ID]} got {run_ids}"
            )
    counts: dict[str, int] = {}
    for table, expected in PHASE2C_FIXTURE_COUNTS.items():
        cursor.execute(f"SELECT COUNT(*) FROM `{schema}`.`{table}`")
        counts[table] = int(cursor.fetchone()[0])
        if schema == PRODUCTION_CORE and counts[table] != expected:
            raise CoreLedgerRemediationError(
                f"Fixture count drift for {table}: expected {expected}, live {counts[table]}"
            )
    return {"run_ids": run_ids, "counts": counts}


def verify_result_tables_empty(cursor: Any, *, schema: str, tables: tuple[str, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in tables:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND TABLE_TYPE='BASE TABLE'",
            (schema, table),
        )
        if int(cursor.fetchone()[0]) != 1:
            raise CoreLedgerRemediationError(f"Required result table missing: {table}")
        cursor.execute(f"SELECT COUNT(*) FROM `{schema}`.`{table}`")
        counts[table] = int(cursor.fetchone()[0])
        if counts[table] != 0:
            raise CoreLedgerRemediationError(f"Result table {table} is not empty")
    return counts


def verify_partial_0004_structure(
    cursor: Any,
    *,
    schema: str,
    sql_0004: Path,
) -> dict[str, Any]:
    sql_text = sql_0004.read_text(encoding="utf-8")
    expected_bodies = parse_expected_create_bodies(sql_text, PARTIAL_0004_TABLES)
    live_digests: dict[str, dict[str, Any]] = {}
    mismatches: dict[str, list[str]] = {}
    for table in PARTIAL_0004_TABLES:
        expected = expected_structural_digest_from_sql(table, expected_bodies[table])
        live = live_structural_digest(cursor, schema, table)
        delta = compare_structural_digests(expected, live)
        if delta:
            mismatches[table] = delta
        live_digests[table] = live
    if mismatches:
        raise CoreLedgerRemediationError(f"Physical 0004 schema diverges from reviewed SQL: {mismatches}")
    return {
        "tables": list(PARTIAL_0004_TABLES),
        "table_digests": {table: digest["table_digest_sha256"] for table, digest in live_digests.items()},
        "physical_schema_verification_hash": package_structural_digest(live_digests),
        "live_digests": live_digests,
    }


def plan_or_apply_remediation(
    *,
    connection_factory: Callable[[], Any],
    target_database: str,
    migrations_dir: Path,
    sql_0004: Path,
    failed_receipt_path: Path,
    backup_path: Path | None,
    remediation_receipt_path: Path,
    approve: bool,
    approved_current_user: str,
    approved_server_attestation_sha256: str | None,
    application_commit: str | None,
    require_failed_receipt_authority: bool = True,
    require_production_fixture: bool = True,
) -> dict[str, Any]:
    """Plan or apply the ledger repair with durable receipt state transitions."""
    if remediation_receipt_path.exists():
        raise CoreLedgerRemediationError(
            f"Refusing to overwrite an existing remediation receipt: {remediation_receipt_path}"
        )
    if require_failed_receipt_authority:
        failed_receipt = load_failed_receipt(failed_receipt_path)
    else:
        failed_receipt = json.loads(failed_receipt_path.read_text(encoding="utf-8"))
    backup_sha = verify_backup_sha256(backup_path) if backup_path is not None else None
    repo_checksums = verify_repository_migration_checksums(migrations_dir, ("0001", "0002", "0003", "0004"))

    connection = connection_factory()
    cursor = connection.cursor()
    committed = False
    inserted_row: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None
    try:
        identity = attest_remediation_target(
            cursor,
            target_database=target_database,
            approved_current_user=approved_current_user,
            approved_server_attestation_sha256=approved_server_attestation_sha256,
        )
        ledger = verify_ledger_partial_0004_preconditions(cursor, schema=target_database)
        if require_production_fixture:
            fixture = verify_fixture_identity(cursor, schema=target_database)
        else:
            fixture = {"run_ids": [], "counts": {}}
            for table in PHASE2C_FIXTURE_COUNTS:
                cursor.execute(f"SELECT COUNT(*) FROM `{target_database}`.`{table}`")
                fixture["counts"][table] = int(cursor.fetchone()[0])
        result_counts = verify_result_tables_empty(
            cursor, schema=target_database, tables=CORE_RESULT_TABLES_TEMPORARY
        )
        schema_report = verify_partial_0004_structure(cursor, schema=target_database, sql_0004=sql_0004)
        remediation_receipt_id = sha256(
            f"{target_database}|{REMEDIATION_EXECUTOR_ID}|{MIGRATION_0004_VERSION}|{_utc_now()}".encode()
        ).hexdigest()
        notes = build_remediation_notes(
            failed_receipt_id=str(failed_receipt.get("receipt_id") or FAILED_PRODUCTION_RECEIPT_ID),
            backup_sha256=backup_sha or "not-provided",
            verification_hash=schema_report["physical_schema_verification_hash"],
        )
        ledger_row = build_ledger_row(
            migration_checksum=repo_checksums["0004"],
            application_commit=application_commit or failed_receipt.get("application_commit"),
            mariadb_version=identity["mariadb_version"],
            receipt_id=remediation_receipt_id,
            notes=notes,
        )
        payload = {
            "receipt_version": RECEIPT_VERSION,
            "status": STATUS_PLANNED,
            "target_database": target_database,
            "operator_identity": getuser(),
            "executor_id": REMEDIATION_EXECUTOR_ID,
            "approved_current_user": approved_current_user,
            "failed_receipt_id": failed_receipt.get("receipt_id"),
            "failed_receipt_path": str(failed_receipt_path),
            "pre_migration_backup_sha256": backup_sha,
            "repository_migration_checksums": repo_checksums,
            "migration_version": MIGRATION_0004_VERSION,
            "migration_name": MIGRATION_0004_NAME,
            "migration_checksum": repo_checksums["0004"],
            "physical_schema_verification_hash": schema_report["physical_schema_verification_hash"],
            "table_digests": schema_report["table_digests"],
            "fixture": fixture,
            "result_row_counts": result_counts,
            "ledger_before": ledger["applied"],
            "identity": identity,
            "planned_ledger_row": ledger_row,
            "ddl_rerun": False,
            "started_at_utc": _utc_now(),
        }
        create_receipt_exclusive(remediation_receipt_path, payload)
        if not approve:
            payload["completed_at_utc"] = _utc_now()
            payload["post_repair_validation"] = {"ledger_contains_0004": False, "mode": "dry_run"}
            replace_receipt_atomic(remediation_receipt_path, payload)
            return payload

        payload["status"] = STATUS_APPLYING
        replace_receipt_atomic(remediation_receipt_path, payload)
        try:
            cursor.execute(
                f"INSERT INTO `{target_database}`.core_schema_migration "
                "(migration_version, migration_name, migration_checksum, applied_at_utc, application_commit, "
                "executor_id, mariadb_version, execution_duration_ms, receipt_id, execution_status, notes) "
                "VALUES (%s,%s,%s,UTC_TIMESTAMP(6),%s,%s,%s,%s,%s,'applied',%s)",
                (
                    ledger_row["migration_version"],
                    ledger_row["migration_name"],
                    ledger_row["migration_checksum"],
                    ledger_row["application_commit"],
                    ledger_row["executor_id"],
                    ledger_row["mariadb_version"],
                    ledger_row["execution_duration_ms"],
                    ledger_row["receipt_id"],
                    ledger_row["notes"],
                ),
            )
        except Exception as exc:
            payload["status"] = STATUS_FAILED_BEFORE_COMMIT
            payload["error_type"] = type(exc).__name__
            payload["completed_at_utc"] = _utc_now()
            replace_receipt_atomic(remediation_receipt_path, payload)
            connection.rollback()
            raise
        try:
            connection.commit()
            committed = True
        except Exception as exc:
            payload["status"] = STATUS_FAILED_BEFORE_COMMIT
            payload["error_type"] = type(exc).__name__
            payload["completed_at_utc"] = _utc_now()
            replace_receipt_atomic(remediation_receipt_path, payload)
            raise
        inserted_row = dict(ledger_row)
        try:
            cursor.execute(
                f"SELECT migration_version, migration_checksum, execution_status, receipt_id, executor_id "
                f"FROM `{target_database}`.core_schema_migration WHERE migration_version=%s",
                (MIGRATION_0004_VERSION,),
            )
            version, checksum, status, receipt_id, executor_id = cursor.fetchone()
            post = {
                "ledger_contains_0004": True,
                "migration_version": str(version),
                "migration_checksum": str(checksum),
                "execution_status": str(status),
                "receipt_id": str(receipt_id),
                "executor_id": str(executor_id),
                "physical_schema_verification_hash": verify_partial_0004_structure(
                    cursor, schema=target_database, sql_0004=sql_0004
                )["physical_schema_verification_hash"],
            }
            if post["migration_checksum"] != MIGRATION_0004_CHECKSUM:
                raise CoreLedgerRemediationError("Post-repair checksum mismatch")
            if post["executor_id"] != REMEDIATION_EXECUTOR_ID:
                raise CoreLedgerRemediationError("Post-repair executor_id mismatch")
            if post["physical_schema_verification_hash"] != schema_report["physical_schema_verification_hash"]:
                raise CoreLedgerRemediationError("Post-repair structural digest drift")
            payload["status"] = STATUS_APPLIED_AND_VERIFIED
            payload["exact_ledger_row_inserted"] = inserted_row
            payload["post_repair_validation"] = post
            payload["completed_at_utc"] = _utc_now()
            replace_receipt_atomic(remediation_receipt_path, payload)
            return payload
        except Exception as exc:
            emergency = {
                **payload,
                "status": STATUS_COMMITTED_BUT_POSTCHECK_FAILED,
                "exact_ledger_row_inserted": inserted_row,
                "error_type": type(exc).__name__,
                "error": "Ledger commit may have succeeded; do not claim rollback; run a fresh read-only audit.",
                "rollback_claimed": False,
                "completed_at_utc": _utc_now(),
            }
            emergency_path = write_emergency_receipt(remediation_receipt_path.parent, emergency)
            try:
                replace_receipt_atomic(remediation_receipt_path, emergency)
            except Exception:
                pass
            raise CoreLedgerRemediationError(
                f"Committed but post-check/finalization failed; emergency_receipt={emergency_path}"
            ) from exc
    except Exception as exc:
        if not committed:
            try:
                connection.rollback()
            except Exception:
                pass
            if payload is not None and remediation_receipt_path.exists():
                if payload.get("status") not in {
                    STATUS_FAILED_BEFORE_COMMIT,
                    STATUS_COMMITTED_BUT_POSTCHECK_FAILED,
                    STATUS_APPLIED_AND_VERIFIED,
                    STATUS_PLANNED,
                }:
                    payload["status"] = STATUS_FAILED_BEFORE_COMMIT
                    payload["error_type"] = type(exc).__name__
                    payload["completed_at_utc"] = _utc_now()
                    try:
                        replace_receipt_atomic(remediation_receipt_path, payload)
                    except Exception:
                        write_emergency_receipt(
                            remediation_receipt_path.parent,
                            {
                                "receipt_version": RECEIPT_VERSION,
                                "status": STATUS_FAILED_BEFORE_COMMIT,
                                "error_type": type(exc).__name__,
                                "completed_at_utc": _utc_now(),
                            },
                        )
            elif payload is None:
                write_emergency_receipt(
                    remediation_receipt_path.parent,
                    {
                        "receipt_version": RECEIPT_VERSION,
                        "status": STATUS_FAILED_BEFORE_COMMIT,
                        "error_type": type(exc).__name__,
                        "completed_at_utc": _utc_now(),
                    },
                )
        raise
    finally:
        cursor.close()
        connection.close()


# Backward-compatible wrappers used by older tests.
def physical_schema_verification_hash(digests: dict[str, dict[str, Any]]) -> str:
    return package_structural_digest(digests)


def expected_table_digest_from_sql(table: str, body: str) -> dict[str, Any]:
    return expected_structural_digest_from_sql(table, body)


def live_table_digest(cursor: Any, schema: str, table: str) -> dict[str, Any]:
    return live_structural_digest(cursor, schema, table)


def compare_table_digests(expected: dict[str, Any], live: dict[str, Any]) -> list[str]:
    return compare_structural_digests(expected, live)
