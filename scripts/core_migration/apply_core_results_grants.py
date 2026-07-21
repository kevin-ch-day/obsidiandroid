#!/usr/bin/env python3
"""Grant Core-results access after migrations 0001-0005 are ledgered.

Dry-run by default. MariaDB GRANT statements implicitly commit; this command
never claims rollback on partial failure and always leaves durable receipts.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import mysql.connector

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from scripts.core_migration.apply_service_accounts import CORE_RESULT_TABLES, CORE_RESULT_WRITER_READS
from obsidiandroid.core_migration.migration_checksums import (
    CORE_RESULT_TABLES_TEMPORARY,
    MIGRATION_CHECKSUMS,
    PRODUCTION_CORE,
    verify_repository_migration_checksums,
)


CORE = PRODUCTION_CORE
REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "database" / "core_migrations"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise RuntimeError("Refusing to overwrite an existing Core-results grant receipt")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def _replace_receipt(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def planned_grant_statements() -> list[str]:
    statements: list[str] = []
    statements.extend(f"GRANT INSERT ON `{CORE}`.`{table}` TO 'obsidiandroid_core_writer'@'localhost'" for table in CORE_RESULT_TABLES)
    statements.extend(f"GRANT SELECT ON `{CORE}`.`{table}` TO 'obsidiandroid_core_writer'@'localhost'" for table in CORE_RESULT_WRITER_READS)
    statements.extend(f"GRANT SELECT ON `{CORE}`.`{table}` TO 'obsidiandroid_core_auditor'@'localhost'" for table in CORE_RESULT_TABLES)
    return statements


def inventory_result_grants(cursor) -> list[dict[str, str]]:
    cursor.execute(
        "SELECT GRANTEE, TABLE_NAME, PRIVILEGE_TYPE FROM information_schema.TABLE_PRIVILEGES "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN (" + ",".join(["%s"] * len(CORE_RESULT_TABLES)) + ") "
        "ORDER BY GRANTEE, TABLE_NAME, PRIVILEGE_TYPE",
        (CORE, *CORE_RESULT_TABLES),
    )
    return [{"grantee": str(g), "table": str(t), "privilege": str(p)} for g, t, p in cursor.fetchall()]


def canonicalize_grants(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: (row["grantee"], row["table"], row["privilege"]))


def expected_grant_set() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    writer = "'obsidiandroid_core_writer'@'localhost'"
    auditor = "'obsidiandroid_core_auditor'@'localhost'"
    for table in CORE_RESULT_TABLES:
        rows.append({"grantee": writer, "table": table, "privilege": "INSERT"})
    for table in CORE_RESULT_WRITER_READS:
        rows.append({"grantee": writer, "table": table, "privilege": "SELECT"})
    for table in CORE_RESULT_TABLES:
        rows.append({"grantee": auditor, "table": table, "privilege": "SELECT"})
    return canonicalize_grants(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--option-file", type=Path, default=Path.home() / ".my.cnf")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise SystemExit("Grant command blocked: receipt already exists")

    repo_checksums = verify_repository_migration_checksums(MIGRATIONS)
    plan = planned_grant_statements()
    payload: dict[str, Any] = {
        "receipt_version": "core-results-grants-v2",
        "status": "planned",
        "target": CORE,
        "required_migrations": sorted(MIGRATION_CHECKSUMS),
        "repository_migration_checksums": repo_checksums,
        "planned_statements": plan,
        "source_access_changed": False,
        "persistence_enabled": False,
        "started_at_utc": _utc_now(),
    }

    if not args.apply:
        payload["completed_at_utc"] = _utc_now()
        _write_receipt(args.receipt, payload)
        print(json.dumps({"dry_run": True, "target": CORE, "planned_statements": len(plan), "receipt": str(args.receipt)}, sort_keys=True))
        return 0

    _write_receipt(args.receipt, payload)
    connection = mysql.connector.connect(option_files=str(args.option_file), autocommit=True)
    cursor = connection.cursor()
    applied: list[str] = []
    try:
        cursor.execute(
            f"SELECT migration_version, migration_checksum, execution_status "
            f"FROM `{CORE}`.core_schema_migration ORDER BY migration_version"
        )
        applied_map = {
            str(version): str(checksum)
            for version, checksum, status in cursor.fetchall()
            if status == "applied"
        }
        if applied_map != MIGRATION_CHECKSUMS:
            raise RuntimeError("Core-results grants require exact applied migrations 0001-0005 with immutable checksums")
        cursor.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE'",
            (CORE,),
        )
        tables = {str(row[0]) for row in cursor.fetchall()}
        if not set(CORE_RESULT_TABLES).issubset(tables):
            raise RuntimeError("Final result tables are missing")
        if set(CORE_RESULT_TABLES_TEMPORARY).intersection(tables):
            raise RuntimeError("Temporary core_* result table names are still present")
        for user in ("obsidiandroid_core_writer", "obsidiandroid_core_auditor"):
            cursor.execute("SELECT COUNT(*) FROM mysql.user WHERE User=%s AND Host='localhost'", (user,))
            if int(cursor.fetchone()[0]) != 1:
                raise RuntimeError("Required Core service account is unavailable")

        before = canonicalize_grants(inventory_result_grants(cursor))
        payload["grants_before"] = before
        unexpected = [row for row in before if row not in expected_grant_set()]
        if unexpected:
            raise RuntimeError(f"Refusing unexpected existing result grants: {unexpected}")
        missing = [statement for statement in plan if True]
        # Apply only missing grants by comparing canonical inventory.
        expected = expected_grant_set()
        missing_rows = [row for row in expected if row not in before]
        statement_by_row = {
            ("INSERT", table, "writer"): f"GRANT INSERT ON `{CORE}`.`{table}` TO 'obsidiandroid_core_writer'@'localhost'"
            for table in CORE_RESULT_TABLES
        }
        statement_by_row.update(
            {
                ("SELECT", table, "writer"): f"GRANT SELECT ON `{CORE}`.`{table}` TO 'obsidiandroid_core_writer'@'localhost'"
                for table in CORE_RESULT_WRITER_READS
            }
        )
        statement_by_row.update(
            {
                ("SELECT", table, "auditor"): f"GRANT SELECT ON `{CORE}`.`{table}` TO 'obsidiandroid_core_auditor'@'localhost'"
                for table in CORE_RESULT_TABLES
            }
        )
        for row in missing_rows:
            role = "writer" if "core_writer" in row["grantee"] else "auditor"
            key = (row["privilege"], row["table"], role)
            statement = statement_by_row[key]
            cursor.execute(statement)
            applied.append(statement)
            after_role = canonicalize_grants(inventory_result_grants(cursor))
            payload["grants_after_last_statement"] = after_role

        final_grants = canonicalize_grants(inventory_result_grants(cursor))
        if final_grants != expected:
            raise RuntimeError("Final grant set does not match the reviewed contract")
        payload["status"] = "applied"
        payload["applied_statements"] = applied
        payload["grants_after"] = final_grants
        payload["post_grant_audit_sha256"] = sha256(
            json.dumps(final_grants, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        payload["completed_at_utc"] = _utc_now()
        _replace_receipt(args.receipt, payload)
        print("CORE RESULTS GRANTS: applied")
        return 0
    except Exception as exc:
        failure = {
            **payload,
            "status": "failed_partial" if applied else "failed",
            "error_type": type(exc).__name__,
            "applied_statements": applied,
            "rollback_claimed": False,
            "completed_at_utc": _utc_now(),
        }
        try:
            failure["grants_after_failure"] = canonicalize_grants(inventory_result_grants(cursor))
        except Exception:
            failure["grants_after_failure"] = None
        _replace_receipt(args.receipt, failure)
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
