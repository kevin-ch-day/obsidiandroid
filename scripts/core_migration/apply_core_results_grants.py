#!/usr/bin/env python3
"""Grant Core-results access to existing local service accounts after migration review.

This does not create users, modify source schemas, or enable pipeline
persistence. It refuses a Core schema without the reviewed result migrations.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

import mysql.connector

from scripts._bootstrap import prepare_script_runtime
prepare_script_runtime(__file__)

from scripts.core_migration.apply_service_accounts import CORE_RESULT_TABLES, CORE_RESULT_WRITER_READS


CORE = "obsidiandroid_core_prod"
REQUIRED = {"0003", "0004", "0005"}


def _write_receipt(path: Path, payload: dict) -> None:
    if path.exists():
        raise RuntimeError("Refusing to overwrite an existing Core-results grant receipt")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--option-file", type=Path, default=Path.home() / ".my.cnf")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps({"dry_run": True, "target": CORE, "required_migrations": sorted(REQUIRED), "result_tables": list(CORE_RESULT_TABLES)}, sort_keys=True))
        return 0
    connection = mysql.connector.connect(option_files=str(args.option_file), autocommit=False)
    cursor = connection.cursor()
    applied: list[str] = []
    try:
        cursor.execute(f"SELECT migration_version FROM `{CORE}`.core_schema_migration WHERE execution_status='applied'")
        versions = {str(row[0]) for row in cursor.fetchall()}
        if not REQUIRED.issubset(versions):
            raise RuntimeError("Core-results grants require applied migrations 0003, 0004, and 0005")
        for user in ("obsidiandroid_core_writer", "obsidiandroid_core_auditor"):
            cursor.execute("SELECT COUNT(*) FROM mysql.user WHERE User=%s AND Host='localhost'", (user,))
            if int(cursor.fetchone()[0]) != 1:
                raise RuntimeError("Required Core service account is unavailable")
        for table in CORE_RESULT_TABLES:
            statement = f"GRANT INSERT ON `{CORE}`.`{table}` TO 'obsidiandroid_core_writer'@'localhost'"
            cursor.execute(statement); applied.append(statement)
        for table in CORE_RESULT_WRITER_READS:
            statement = f"GRANT SELECT ON `{CORE}`.`{table}` TO 'obsidiandroid_core_writer'@'localhost'"
            cursor.execute(statement); applied.append(statement)
        for table in CORE_RESULT_TABLES:
            statement = f"GRANT SELECT ON `{CORE}`.`{table}` TO 'obsidiandroid_core_auditor'@'localhost'"
            cursor.execute(statement); applied.append(statement)
        connection.commit()
        _write_receipt(args.receipt, {"receipt_version": "core-results-grants-v1", "status": "applied", "target": CORE, "applied_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"), "required_migrations": sorted(REQUIRED), "grant_statements": applied, "source_access_changed": False, "persistence_enabled": False})
        print("CORE RESULTS GRANTS: applied")
        return 0
    except Exception as exc:
        connection.rollback()
        if not args.receipt.exists():
            _write_receipt(args.receipt, {"receipt_version": "core-results-grants-v1", "status": "failed", "target": CORE, "failed_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"), "error_type": type(exc).__name__, "applied_grants": applied, "source_access_changed": False})
        raise
    finally:
        cursor.close(); connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
