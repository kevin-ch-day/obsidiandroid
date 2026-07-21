#!/usr/bin/env python3
"""Apply missing Core migrations to a nonempty, already-provisioned Core schema.

Distinct from provision_core_schema.py (empty-target only). Defaults to dry-run.
Never imports evidence, never applies grants, never enables persistence.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from getpass import getuser
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any

import mysql.connector

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.core_migration.authorization import mariadb_server_attestation
from obsidiandroid.core_migration.executor import apply_migrations, discover_migrations
from obsidiandroid.core_migration.migration_checksums import (
    CORE_RESULT_TABLES_TEMPORARY,
    MIGRATION_CHECKSUMS,
    PRODUCTION_CORE,
    verify_repository_migration_checksums,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "database" / "core_migrations"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite an existing upgrade receipt: {path}")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def _connect(option_file: Path, database: str | None = None):
    kwargs: dict[str, Any] = {"option_files": str(option_file), "autocommit": False}
    if database:
        kwargs["database"] = database
    return mysql.connector.connect(**kwargs)


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def inspect_upgrade_state(cursor, target: str) -> dict[str, Any]:
    cursor.execute("SELECT DATABASE(), CURRENT_USER(), VERSION()")
    database_name, current_user, version = cursor.fetchone()
    cursor.execute("SELECT @@hostname, @@port, @@server_id, @@version, @@version_comment")
    hostname, port, server_id, server_version, version_comment = cursor.fetchone()
    attestation = {
        "attestation_version": "mariadb-server-attestation-v1",
        "hostname": str(hostname),
        "port": int(port),
        "server_id": int(server_id),
        "version": str(server_version),
        "version_comment": str(version_comment),
    }
    attestation["sha256"] = mariadb_server_attestation(**{k: attestation[k] for k in ("hostname", "port", "server_id", "version", "version_comment")})
    cursor.execute(
        f"SELECT migration_version, migration_checksum, execution_status, receipt_id "
        f"FROM `{target}`.core_schema_migration ORDER BY migration_version"
    )
    rows = [(str(v), str(c), str(s), None if r is None else str(r)) for v, c, s, r in cursor.fetchall()]
    applied = {version: checksum for version, checksum, status, _receipt in rows if status == "applied"}
    cursor.execute(
        "SELECT TABLE_NAME FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME",
        (target,),
    )
    tables = [str(row[0]) for row in cursor.fetchall()]
    return {
        "database": str(database_name),
        "current_user": str(current_user),
        "mariadb_version": str(version),
        "server_attestation": attestation,
        "ledger_rows": [
            {"version": v, "checksum": c, "status": s, "receipt_id": r} for v, c, s, r in rows
        ],
        "applied": applied,
        "tables": tables,
    }


def detect_unledgered_physical_ddl(tables: list[str], applied: dict[str, str]) -> list[str]:
    issues: list[str] = []
    temporary = set(CORE_RESULT_TABLES_TEMPORARY)
    present_temporary = temporary.intersection(tables)
    if present_temporary and "0004" not in applied and "0005" not in applied and "0003" in applied:
        issues.append("unledgered_partial_0004_or_result_ddl")
    final_present = any(name in tables for name in ("label_contract", "model_execution", "prediction"))
    if final_present and "0005" not in applied:
        issues.append("final_result_names_without_0005_ledger")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--option-file", type=Path, default=Path.home() / ".my.cnf")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--approve-production-upgrade", action="store_true")
    parser.add_argument("--approved-current-user", required=True)
    parser.add_argument("--approved-server-attestation-sha256", default=None)
    parser.add_argument("--target-database", default=PRODUCTION_CORE)
    parser.add_argument(
        "--allow-unledgered-physical-ddl-after-reconciliation",
        action="store_true",
        help="Required only when a reviewed reconciliation contract has already closed partial DDL",
    )
    args = parser.parse_args()
    if args.receipt.exists():
        raise SystemExit(f"Upgrade blocked: receipt already exists: {args.receipt}")
    if not args.option_file.is_file():
        raise SystemExit("Upgrade blocked: option file unavailable")

    repo_checksums = verify_repository_migration_checksums(MIGRATIONS)
    head = _git_head()
    discovered = discover_migrations(MIGRATIONS)
    connection = _connect(args.option_file, args.target_database)
    cursor = connection.cursor()
    try:
        state = inspect_upgrade_state(cursor, args.target_database)
    finally:
        cursor.close()
        connection.close()

    if state["database"] != args.target_database:
        raise SystemExit("Upgrade blocked: DATABASE() mismatch")
    if state["current_user"] != args.approved_current_user:
        raise SystemExit("Upgrade blocked: CURRENT_USER() mismatch")
    if args.approved_server_attestation_sha256 and (
        state["server_attestation"]["sha256"] != args.approved_server_attestation_sha256
    ):
        raise SystemExit("Upgrade blocked: server attestation mismatch")

    applied = state["applied"]
    for version, checksum in applied.items():
        if version in MIGRATION_CHECKSUMS and checksum != MIGRATION_CHECKSUMS[version]:
            raise SystemExit(f"Upgrade blocked: ledger checksum mismatch for {version}")
    expected_prefix = [f"{n:04d}" for n in range(1, len(applied) + 1)]
    if sorted(applied) != expected_prefix:
        raise SystemExit(f"Upgrade blocked: ledger versions are not contiguous from 0001: {sorted(applied)}")

    missing = [item.version for item in discovered if item.version not in applied]
    issues = detect_unledgered_physical_ddl(state["tables"], applied)
    if issues and not args.allow_unledgered_physical_ddl_after_reconciliation:
        raise SystemExit(
            "Upgrade blocked: unledgered physical DDL detected; "
            "close the reconciliation contract first or pass "
            "--allow-unledgered-physical-ddl-after-reconciliation after review: "
            + ",".join(issues)
        )

    receipt = {
        "receipt_version": "core-nonempty-upgrade-v1",
        "status": "planned",
        "dry_run": not args.approve_production_upgrade,
        "target_database": args.target_database,
        "operator_identity": getuser(),
        "repository_head": head,
        "repository_migration_checksums": repo_checksums,
        "approved_current_user": args.approved_current_user,
        "server_attestation": state["server_attestation"],
        "ledger_before": applied,
        "missing_migrations": missing,
        "planned_only": missing,
        "imports": False,
        "grants": False,
        "persistence_enabled": False,
        "unledgered_physical_ddl_issues": issues,
        "started_at_utc": _utc_now(),
    }
    if not args.approve_production_upgrade:
        receipt["completed_at_utc"] = _utc_now()
        _write_receipt(args.receipt, receipt)
        print(json.dumps({"status": "planned", "missing_migrations": missing, "receipt": str(args.receipt)}, indent=2, sort_keys=True))
        return 0

    if args.target_database == PRODUCTION_CORE and not args.approved_server_attestation_sha256:
        raise SystemExit("Production upgrade requires --approved-server-attestation-sha256")

    factory = lambda database: _connect(args.option_file, database)
    result = apply_migrations(
        target_database=args.target_database,
        migrations_dir=MIGRATIONS,
        connection_factory=factory,
        dry_run=False,
        allow_production=args.target_database == PRODUCTION_CORE,
        executor_id="obsidiandroid-core-nonempty-upgrader",
        application_commit=head,
        receipt_path=None,
    )
    receipt["status"] = "applied"
    receipt["dry_run"] = False
    receipt["executor_result"] = {
        "status": result["status"],
        "applied": result["applied"],
        "skipped": result["skipped"],
        "invocation_id": result["invocation_id"],
        "migration_receipt_ids": result["migration_receipt_ids"],
    }
    receipt["completed_at_utc"] = _utc_now()
    _write_receipt(args.receipt, receipt)
    print(json.dumps({"status": "applied", "applied": result["applied"], "receipt": str(args.receipt)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
