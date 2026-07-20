#!/usr/bin/env python3
"""Receipted remediation for the partial production 0004 ledger state.

Default mode verifies physical DDL, fixture integrity, and the failed receipt,
then writes a dry-run remediation plan.  It never re-runs DDL.

Production ledger INSERT requires an explicit --approve-ledger-repair flag and
writes a new non-overwriting remediation receipt beside the failed authority
receipt.  Do not execute the approved INSERT until an operator confirms.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from getpass import getuser
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import mysql.connector

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.core_migration.ledger_remediation import (
    EXPECTED_FIXTURE_COUNTS,
    FAILED_PRODUCTION_RECEIPT_ID,
    MIGRATION_0004_CHECKSUM,
    MIGRATION_0004_NAME,
    MIGRATION_0004_VERSION,
    PARTIAL_0004_TABLES,
    PRE_MIGRATION_BACKUP_SHA256,
    REMEDIATION_EXECUTOR_ID,
    CoreLedgerRemediationError,
    build_ledger_row,
    build_remediation_notes,
    compare_table_digests,
    expected_table_digest_from_sql,
    live_table_digest,
    load_failed_receipt,
    parse_expected_create_bodies,
    physical_schema_verification_hash,
    verify_backup_sha256,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "database" / "core_migrations"
SQL_0004 = MIGRATIONS_DIR / "0004_core_label_and_confusion_contracts.sql"
TARGET = "obsidiandroid_core_prod"
DEFAULT_PROVISIONING_DIR = Path(
    "/mnt/MERCURY_DATA_V2/obsidiandroid_core_results_provisioning/20260720T153822Z"
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _connect(option_file: Path):
    return mysql.connector.connect(
        option_files=str(option_file),
        database=TARGET,
        autocommit=False,
    )


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise CoreLedgerRemediationError(f"Refusing to overwrite an existing remediation receipt: {path}")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def _verify_file_checksum() -> str:
    digest = sha256(SQL_0004.read_bytes()).hexdigest()
    if digest != MIGRATION_0004_CHECKSUM:
        raise CoreLedgerRemediationError("Reviewed 0004 SQL checksum does not match the incident authority")
    return digest


def _collect_fixture_counts(cursor) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, expected in EXPECTED_FIXTURE_COUNTS.items():
        cursor.execute(f"SELECT COUNT(*) FROM `{TARGET}`.`{table}`")
        counts[table] = int(cursor.fetchone()[0])
        if counts[table] != expected:
            raise CoreLedgerRemediationError(
                f"Fixture count drift for {table}: expected {expected}, live {counts[table]}"
            )
    return counts


def _collect_result_row_counts(cursor) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in PARTIAL_0004_TABLES:
        cursor.execute(f"SELECT COUNT(*) FROM `{TARGET}`.`{table}`")
        counts[table] = int(cursor.fetchone()[0])
        if counts[table] != 0:
            raise CoreLedgerRemediationError(f"Partial 0004 table {table} is not empty")
    return counts


def _verify_ledger_preconditions(cursor) -> dict[str, str]:
    cursor.execute(
        f"SELECT migration_version, migration_checksum, execution_status, receipt_id "
        f"FROM `{TARGET}`.core_schema_migration ORDER BY migration_version"
    )
    rows = cursor.fetchall()
    applied = {
        str(version): str(checksum)
        for version, checksum, status, _receipt in rows
        if status == "applied"
    }
    if set(applied) != {"0001", "0002", "0003"}:
        raise CoreLedgerRemediationError(
            f"Ledger must contain exactly applied 0001-0003 before repair; found {sorted(applied)}"
        )
    if MIGRATION_0004_VERSION in {str(version) for version, *_ in rows}:
        raise CoreLedgerRemediationError("Refusing repair: 0004 is already present in the ledger")
    receipt_ids = [str(receipt) for *_rest, receipt in rows if receipt is not None]
    if FAILED_PRODUCTION_RECEIPT_ID not in receipt_ids:
        raise CoreLedgerRemediationError("Ledger is missing the failed production receipt_id on 0003")
    return applied


def verify_partial_0004_state(cursor) -> dict[str, Any]:
    """Verify production physical 0004 tables against reviewed SQL."""
    sql_text = SQL_0004.read_text(encoding="utf-8")
    expected_bodies = parse_expected_create_bodies(sql_text)
    live_digests: dict[str, dict[str, Any]] = {}
    mismatches: dict[str, list[str]] = {}
    for table in PARTIAL_0004_TABLES:
        expected = expected_table_digest_from_sql(table, expected_bodies[table])
        live = live_table_digest(cursor, TARGET, table)
        delta = compare_table_digests(expected, live)
        if delta:
            mismatches[table] = delta
        live_digests[table] = live
    if mismatches:
        raise CoreLedgerRemediationError(f"Physical 0004 schema diverges from reviewed SQL: {mismatches}")
    return {
        "tables": list(PARTIAL_0004_TABLES),
        "physical_schema_verification_hash": physical_schema_verification_hash(live_digests),
        "live_digests": live_digests,
    }


def plan_or_apply(
    *,
    option_file: Path,
    failed_receipt_path: Path,
    backup_path: Path,
    remediation_receipt_path: Path,
    approve: bool,
    application_commit: str | None,
) -> dict[str, Any]:
    failed_receipt = load_failed_receipt(failed_receipt_path)
    backup_sha = verify_backup_sha256(backup_path)
    migration_checksum = _verify_file_checksum()
    connection = _connect(option_file)
    cursor = connection.cursor()
    inserted_row: dict[str, Any] | None = None
    try:
        applied = _verify_ledger_preconditions(cursor)
        fixture_counts = _collect_fixture_counts(cursor)
        result_counts = _collect_result_row_counts(cursor)
        schema_report = verify_partial_0004_state(cursor)
        cursor.execute("SELECT VERSION()")
        mariadb_version = str(cursor.fetchone()[0])
        remediation_receipt_id = sha256(
            f"{TARGET}|{REMEDIATION_EXECUTOR_ID}|{MIGRATION_0004_VERSION}|{_utc_now()}".encode()
        ).hexdigest()
        notes = build_remediation_notes(
            failed_receipt_id=FAILED_PRODUCTION_RECEIPT_ID,
            backup_sha256=backup_sha,
            verification_hash=schema_report["physical_schema_verification_hash"],
        )
        ledger_row = build_ledger_row(
            migration_checksum=migration_checksum,
            application_commit=application_commit or failed_receipt.get("application_commit"),
            mariadb_version=mariadb_version,
            receipt_id=remediation_receipt_id,
            notes=notes,
        )
        payload: dict[str, Any] = {
            "receipt_version": "core-0004-ledger-remediation-v1",
            "status": "planned" if not approve else "applied",
            "target_database": TARGET,
            "operator_identity": getuser(),
            "executor_id": REMEDIATION_EXECUTOR_ID,
            "failed_receipt_id": FAILED_PRODUCTION_RECEIPT_ID,
            "failed_receipt_path": str(failed_receipt_path),
            "pre_migration_backup_sha256": backup_sha,
            "migration_version": MIGRATION_0004_VERSION,
            "migration_name": MIGRATION_0004_NAME,
            "migration_checksum": migration_checksum,
            "physical_schema_verification_hash": schema_report["physical_schema_verification_hash"],
            "fixture_counts": fixture_counts,
            "partial_0004_row_counts": result_counts,
            "ledger_before": applied,
            "planned_ledger_row": ledger_row,
            "ddl_rerun": False,
            "started_at_utc": _utc_now(),
        }
        if not approve:
            payload["completed_at_utc"] = _utc_now()
            payload["post_repair_validation"] = {
                "ledger_contains_0004": False,
                "mode": "dry_run",
            }
            _write_receipt(remediation_receipt_path, payload)
            return payload

        cursor.execute(
            f"INSERT INTO `{TARGET}`.core_schema_migration "
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
        connection.commit()
        inserted_row = dict(ledger_row)
        cursor.execute(
            f"SELECT migration_version, migration_checksum, execution_status, receipt_id, executor_id "
            f"FROM `{TARGET}`.core_schema_migration WHERE migration_version=%s",
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
            "fixture_counts": _collect_fixture_counts(cursor),
            "partial_0004_row_counts": _collect_result_row_counts(cursor),
            "physical_schema_verification_hash": verify_partial_0004_state(cursor)[
                "physical_schema_verification_hash"
            ],
        }
        if post["migration_checksum"] != MIGRATION_0004_CHECKSUM:
            raise CoreLedgerRemediationError("Post-repair checksum mismatch")
        if post["executor_id"] != REMEDIATION_EXECUTOR_ID:
            raise CoreLedgerRemediationError("Post-repair executor_id mismatch")
        payload["status"] = "applied"
        payload["exact_ledger_row_inserted"] = inserted_row
        payload["post_repair_validation"] = post
        payload["completed_at_utc"] = _utc_now()
        _write_receipt(remediation_receipt_path, payload)
        return payload
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--option-file", type=Path, default=Path.home() / ".my.cnf")
    parser.add_argument(
        "--provisioning-dir",
        type=Path,
        default=DEFAULT_PROVISIONING_DIR,
        help="External directory holding the failed receipt and pre-migration backup",
    )
    parser.add_argument(
        "--remediation-receipt",
        type=Path,
        help="Output path for the new remediation receipt (default: beside the failed receipt)",
    )
    parser.add_argument(
        "--application-commit",
        default=None,
        help="Optional application commit recorded on the repaired ledger row",
    )
    parser.add_argument(
        "--approve-ledger-repair",
        action="store_true",
        help="Actually INSERT the verified 0004 ledger row. Default is dry-run only.",
    )
    args = parser.parse_args()
    if not args.option_file.is_file():
        raise SystemExit("Remediation blocked: protected MariaDB option file is unavailable")
    failed_receipt = args.provisioning_dir / "production_migration_receipt.json"
    backup = args.provisioning_dir / "pre_0003_0005_core.sql.gz"
    remediation_receipt = args.remediation_receipt or (
        args.provisioning_dir / f"0004_ledger_remediation_receipt_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    result = plan_or_apply(
        option_file=args.option_file,
        failed_receipt_path=failed_receipt,
        backup_path=backup,
        remediation_receipt_path=remediation_receipt,
        approve=bool(args.approve_ledger_repair),
        application_commit=args.application_commit,
    )
    print(json.dumps({
        "status": result["status"],
        "remediation_receipt": str(remediation_receipt),
        "physical_schema_verification_hash": result["physical_schema_verification_hash"],
        "ddl_rerun": False,
        "approve_ledger_repair": bool(args.approve_ledger_repair),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
