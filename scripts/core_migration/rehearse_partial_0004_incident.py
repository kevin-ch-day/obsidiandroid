#!/usr/bin/env python3
"""Disposable rehearsal of the partial-0004 incident recovery path.

Never connects to production. Constructs the logical incident in a disposable
schema, remediates the ledger, applies 0005, and verifies the final contract.
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

from obsidiandroid.core_migration.executor import apply_migrations, discover_migrations, split_sql_statements
from obsidiandroid.core_migration.ledger_remediation import plan_or_apply_remediation
from obsidiandroid.core_migration.migration_checksums import (
    CORE_FOUNDATION_TABLES,
    CORE_RESULT_TABLES_FINAL,
    CORE_RESULT_TABLES_TEMPORARY,
    FAILED_PRODUCTION_RECEIPT_ID,
    MIGRATION_CHECKSUMS,
    PARTIAL_0004_TABLES,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "database" / "core_migrations"
SQL_0004 = MIGRATIONS / "0004_core_label_and_confusion_contracts.sql"


def _utc_target() -> str:
    return "od_core_phase2b_validate_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _connect(option_file: Path, database: str | None = None):
    kwargs: dict[str, Any] = {"option_files": str(option_file), "autocommit": False}
    if database:
        kwargs["database"] = database
    return mysql.connector.connect(**kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--option-file", type=Path, default=Path.home() / ".my.cnf")
    parser.add_argument("--target", default=_utc_target())
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--keep-schema", action="store_true")
    args = parser.parse_args()
    if not args.option_file.is_file():
        raise SystemExit("option file unavailable")
    args.receipt_dir.mkdir(parents=True, exist_ok=True)

    target = args.target
    admin = _connect(args.option_file)
    cursor = admin.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (target,))
        if int(cursor.fetchone()[0]):
            raise SystemExit("target already exists")
        cursor.execute(f"CREATE DATABASE `{target}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        admin.commit()
    finally:
        cursor.close()
        admin.close()

    factory = lambda database: _connect(args.option_file, database)
    try:
        # 1-2: apply/ledger 0001-0003 only by temporarily excluding later files via filtered dir is hard;
        # instead apply all then we need incident shape. Better: apply migrations from a temp dir with only 0001-0003,
        # then execute 0004 DDL manually without ledger.
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory(prefix="od-partial0004-") as temp:
            mig = Path(temp) / "migrations"
            mig.mkdir()
            for version in ("0001", "0002", "0003"):
                src = next(MIGRATIONS.glob(f"{version}_*.sql"))
                shutil.copy2(src, mig / src.name)
            first = apply_migrations(
                target_database=target,
                migrations_dir=mig,
                connection_factory=factory,
                dry_run=False,
                executor_id="obsidiandroid-core-disposable-incident-rehearsal",
                receipt_path=args.receipt_dir / "apply_0001_0003.json",
            )
            assert first["applied"] == ["0001", "0002", "0003"]

            # Force 0003 receipt_id to the incident authority for production-shaped attestation paths that care.
            conn = factory(target)
            cur = conn.cursor()
            try:
                cur.execute(
                    "UPDATE core_schema_migration SET receipt_id=%s WHERE migration_version='0003'",
                    (FAILED_PRODUCTION_RECEIPT_ID,),
                )
                conn.commit()
                # 3: execute 0004 DDL without ledger row
                for statement in split_sql_statements(SQL_0004.read_text(encoding="utf-8")):
                    cur.execute(statement)
                conn.commit()
                for table in PARTIAL_0004_TABLES:
                    cur.execute(f"SELECT COUNT(*) FROM `{table}`")
                    assert int(cur.fetchone()[0]) == 0
                cur.execute("SELECT CURRENT_USER()")
                current_user = str(cur.fetchone()[0])
            finally:
                cur.close()
                conn.close()

            failed_receipt = {
                "receipt_id": FAILED_PRODUCTION_RECEIPT_ID,
                "status": "failed",
                "error_type": "IntegrityError",
                "applied": ["0003"],
                "application_commit": "rehearsal",
            }
            failed_path = args.receipt_dir / "synthetic_failed_receipt.json"
            failed_path.write_text(json.dumps(failed_receipt, indent=2) + "\n", encoding="utf-8")
            remediation_receipt = args.receipt_dir / "remediation.json"
            repair = plan_or_apply_remediation(
                connection_factory=lambda: factory(target),
                target_database=target,
                migrations_dir=MIGRATIONS,
                sql_0004=SQL_0004,
                failed_receipt_path=failed_path,
                backup_path=None,
                remediation_receipt_path=remediation_receipt,
                approve=True,
                approved_current_user=current_user,
                approved_server_attestation_sha256=None,
                application_commit="rehearsal",
                require_failed_receipt_authority=True,
                require_production_fixture=False,
            )
            assert repair["status"] == "applied_and_verified"

            # 7: apply 0005 via fixed executor against full migrations dir (0001-0004 skip, 0005 apply)
            # Need 0004 file present for discover; ledger already has 0004.
            fifth = apply_migrations(
                target_database=target,
                migrations_dir=MIGRATIONS,
                connection_factory=factory,
                dry_run=False,
                allow_production=False,
                executor_id="obsidiandroid-core-disposable-incident-rehearsal",
                receipt_path=args.receipt_dir / "apply_0005.json",
            )
            assert fifth["applied"] == ["0005"]
            assert fifth["skipped"] == ["0001", "0002", "0003", "0004"]

            conn = factory(target)
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT migration_version, receipt_id FROM core_schema_migration "
                    "WHERE execution_status='applied' ORDER BY migration_version"
                )
                rows = cur.fetchall()
                versions = [str(v) for v, _r in rows]
                receipt_ids = [str(r) for _v, r in rows if r is not None]
                assert versions == ["0001", "0002", "0003", "0004", "0005"]
                assert len(receipt_ids) == len(set(receipt_ids))
                cur.execute(
                    "SELECT TABLE_NAME FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE'",
                    (target,),
                )
                tables = {str(row[0]) for row in cur.fetchall()}
                assert len(tables) == 19
                assert set(CORE_RESULT_TABLES_FINAL).issubset(tables)
                assert set(CORE_FOUNDATION_TABLES).issubset(tables)
                assert not set(CORE_RESULT_TABLES_TEMPORARY).intersection(tables)
            finally:
                cur.close()
                conn.close()

            rerun = apply_migrations(
                target_database=target,
                migrations_dir=MIGRATIONS,
                connection_factory=factory,
                dry_run=False,
                executor_id="obsidiandroid-core-disposable-incident-rehearsal",
            )
            assert rerun["skipped"] == ["0001", "0002", "0003", "0004", "0005"]
            assert rerun["applied"] == []

        summary = {
            "schema": target,
            "status": "passed",
            "migrations": ["0001", "0002", "0003", "0004", "0005"],
            "remediation_status": repair["status"],
            "checksums": MIGRATION_CHECKSUMS,
        }
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
