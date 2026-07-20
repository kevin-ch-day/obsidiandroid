#!/usr/bin/env python3
"""Apply reviewed Core migrations 0001-0005 in a fresh disposable schema.

This rehearses the post-receipt-id-fix migration path without touching
production Core, sources, grants, or persistence. The disposable schema is
dropped unless --keep-schema is passed.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import mysql.connector

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.core_migration.executor import apply_migrations, validate_target_name


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "database" / "core_migrations"
FINAL_RESULT_TABLES = (
    "run_stage",
    "feature_contract",
    "split_ledger",
    "model_execution",
    "model_metric",
    "prediction",
    "experiment",
    "experiment_metric",
    "permission_measure",
    "label_contract",
    "label_assignment",
    "confusion_cell",
)
FOUNDATION_TABLES = (
    "core_schema_migration",
    "core_profile",
    "core_source_snapshot",
    "core_run",
    "core_run_sample",
    "core_artifact",
    "core_quality_finding",
)


def _utc_target() -> str:
    return "od_core_phase2b_validate_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _connect(option_file: Path, database: str | None = None):
    kwargs: dict[str, Any] = {"option_files": str(option_file), "autocommit": False}
    if database:
        kwargs["database"] = database
    return mysql.connector.connect(**kwargs)


def _inspect(factory, target: str) -> dict[str, Any]:
    connection = factory(target)
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME",
            (target,),
        )
        tables = [str(row[0]) for row in cursor.fetchall()]
        cursor.execute(
            "SELECT migration_version, receipt_id FROM core_schema_migration "
            "WHERE execution_status='applied' ORDER BY migration_version"
        )
        ledger = [(str(version), None if receipt is None else str(receipt)) for version, receipt in cursor.fetchall()]
        receipt_ids = [receipt for _version, receipt in ledger if receipt is not None]
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA=%s AND UNIQUE_CONSTRAINT_SCHEMA <> %s",
            (target, target),
        )
        cross_schema = int(cursor.fetchone()[0])
        return {
            "tables": tables,
            "table_count": len(tables),
            "ledger": [{"version": version, "receipt_id": receipt} for version, receipt in ledger],
            "ledger_receipt_ids_unique": len(receipt_ids) == len(set(receipt_ids)),
            "cross_schema_foreign_keys": cross_schema,
            "final_result_tables_present": all(name in tables for name in FINAL_RESULT_TABLES),
            "foundation_tables_present": all(name in tables for name in FOUNDATION_TABLES),
            "temporary_result_tables_absent": not any(name.startswith("core_") and name not in FOUNDATION_TABLES for name in tables),
        }
    finally:
        cursor.close()
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=_utc_target())
    parser.add_argument("--option-file", type=Path, default=Path.home() / ".my.cnf")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--keep-schema", action="store_true")
    args = parser.parse_args()
    target = validate_target_name(args.target)
    if not args.option_file.is_file():
        raise SystemExit("Refusing: protected MariaDB option file is unavailable")
    if args.receipt.exists():
        raise SystemExit("Refusing to overwrite an existing disposable migration receipt")

    admin = _connect(args.option_file)
    cursor = admin.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (target,))
        if int(cursor.fetchone()[0]):
            raise SystemExit("Refusing: disposable target already exists")
        cursor.execute(f"CREATE DATABASE `{target}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        admin.commit()
    finally:
        cursor.close()
        admin.close()

    factory = lambda database: _connect(args.option_file, database)
    try:
        receipt = apply_migrations(
            target_database=target,
            migrations_dir=MIGRATIONS,
            connection_factory=factory,
            dry_run=False,
            executor_id="obsidiandroid-core-disposable-migration-rehearsal",
            receipt_path=args.receipt,
        )
        inspection = _inspect(factory, target)
        rerun = apply_migrations(
            target_database=target,
            migrations_dir=MIGRATIONS,
            connection_factory=factory,
            dry_run=False,
            executor_id="obsidiandroid-core-disposable-migration-rehearsal",
        )
        summary = {
            "schema": target,
            "status": receipt["status"],
            "applied": receipt["applied"],
            "migration_receipt_ids_unique": len(set(receipt["migration_receipt_ids"].values()))
            == len(receipt["migration_receipt_ids"]),
            "inspection": inspection,
            "rerun_skipped": rerun["skipped"],
        }
        if not (
            summary["status"] == "applied"
            and summary["applied"] == ["0001", "0002", "0003", "0004", "0005"]
            and summary["migration_receipt_ids_unique"]
            and inspection["table_count"] == 19
            and inspection["ledger_receipt_ids_unique"]
            and inspection["cross_schema_foreign_keys"] == 0
            and inspection["final_result_tables_present"]
            and inspection["foundation_tables_present"]
            and inspection["temporary_result_tables_absent"]
            and rerun["skipped"] == ["0001", "0002", "0003", "0004", "0005"]
        ):
            raise SystemExit(f"Disposable migration rehearsal failed contract: {json.dumps(summary, sort_keys=True)}")
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    finally:
        if not args.keep_schema:
            cleanup = _connect(args.option_file)
            cleanup_cursor = cleanup.cursor()
            try:
                cleanup_cursor.execute(f"DROP DATABASE IF EXISTS `{target}`")
                cleanup.commit()
            finally:
                cleanup_cursor.close()
                cleanup.close()


if __name__ == "__main__":
    raise SystemExit(main())
