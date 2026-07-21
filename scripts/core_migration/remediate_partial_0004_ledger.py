#!/usr/bin/env python3
"""Receipted remediation for the partial production 0004 ledger state.

Default mode verifies physical DDL, fixture integrity, and the failed receipt,
then writes a durable planned remediation receipt.  It never re-runs DDL.

Production ledger INSERT requires --approve-ledger-repair plus explicit
identity/attestation inputs.  Do not execute the approved INSERT until an
operator confirms.
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

from obsidiandroid.core_migration.ledger_remediation import (
    PRODUCTION_CORE,
    CoreLedgerRemediationError,
    plan_or_apply_remediation,
)
from obsidiandroid.core_migration.migration_checksums import PRODUCTION_CORE as TARGET


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "database" / "core_migrations"
SQL_0004 = MIGRATIONS_DIR / "0004_core_label_and_confusion_contracts.sql"
DEFAULT_PROVISIONING_DIR = Path(
    "/mnt/MERCURY_DATA_V2/obsidiandroid_core_results_provisioning/20260720T153822Z"
)


def _connect(option_file: Path, database: str):
    return mysql.connector.connect(
        option_files=str(option_file),
        database=database,
        autocommit=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--option-file", type=Path, default=Path.home() / ".my.cnf")
    parser.add_argument("--provisioning-dir", type=Path, default=DEFAULT_PROVISIONING_DIR)
    parser.add_argument("--remediation-receipt", type=Path, required=True)
    parser.add_argument("--application-commit", default=None)
    parser.add_argument("--approve-ledger-repair", action="store_true")
    parser.add_argument(
        "--approved-current-user",
        required=True,
        help="Exact CURRENT_USER() value required before any remediation write",
    )
    parser.add_argument(
        "--approved-server-attestation-sha256",
        default=None,
        help="Optional approved MariaDB server attestation hash; required for production approve mode",
    )
    parser.add_argument(
        "--target-database",
        default=TARGET,
        help="Core schema target (production default; disposable rehearsal may override)",
    )
    args = parser.parse_args()
    if not args.option_file.is_file():
        raise SystemExit("Remediation blocked: protected MariaDB option file is unavailable")
    if args.remediation_receipt.exists():
        raise SystemExit(f"Remediation blocked: receipt already exists: {args.remediation_receipt}")
    if args.approve_ledger_repair and args.target_database == PRODUCTION_CORE:
        if not args.approved_server_attestation_sha256:
            raise SystemExit("Production approve mode requires --approved-server-attestation-sha256")

    failed_receipt = args.provisioning_dir / "production_migration_receipt.json"
    backup = args.provisioning_dir / "pre_0003_0005_core.sql.gz"
    require_authority = args.target_database == PRODUCTION_CORE
    result = plan_or_apply_remediation(
        connection_factory=lambda: _connect(args.option_file, args.target_database),
        target_database=args.target_database,
        migrations_dir=MIGRATIONS_DIR,
        sql_0004=SQL_0004,
        failed_receipt_path=failed_receipt,
        backup_path=backup if backup.is_file() else None,
        remediation_receipt_path=args.remediation_receipt,
        approve=bool(args.approve_ledger_repair),
        approved_current_user=args.approved_current_user,
        approved_server_attestation_sha256=args.approved_server_attestation_sha256,
        application_commit=args.application_commit,
        require_failed_receipt_authority=require_authority,
        require_production_fixture=require_authority,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "remediation_receipt": str(args.remediation_receipt),
                "physical_schema_verification_hash": result["physical_schema_verification_hash"],
                "ddl_rerun": False,
                "approve_ledger_repair": bool(args.approve_ledger_repair),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
