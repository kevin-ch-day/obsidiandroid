#!/usr/bin/env python3
"""Read-only Core-auditor reconciliation for one executed Phase 2C plan.

The command cannot create an extract, authorization, or import. It reads only
the six Core evidence tables through the dedicated auditor identity, projects
the plan-bound rows for one run, and writes a new external verification receipt.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from typing import Any

import mysql.connector

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.core_migration.authorization import PRODUCTION_CORE_SCHEMA
from obsidiandroid.core_migration.importer import validate_import_plan
from obsidiandroid.core_migration.mapping import CoreImportError
from obsidiandroid.core_migration.private_credentials import Phase2CCredentialRole, load_phase2c_credentials
from obsidiandroid.core_migration.reconciliation import reconcile_destination_rows


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUDITOR_ACCOUNT = "obsidiandroid_core_auditor@localhost"
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TABLES = {
    "core_profile": ("SELECT {columns} FROM core_profile p JOIN core_run r ON r.profile_id=p.profile_id WHERE r.run_id=%s", "p"),
    "core_source_snapshot": ("SELECT {columns} FROM core_source_snapshot s JOIN core_run r ON r.source_snapshot_id=s.source_snapshot_id WHERE r.run_id=%s", "s"),
    "core_run": ("SELECT {columns} FROM core_run r WHERE r.run_id=%s", "r"),
    "core_run_sample": ("SELECT {columns} FROM core_run_sample s WHERE s.run_id=%s", "s"),
    "core_artifact": ("SELECT {columns} FROM core_artifact a WHERE a.run_id=%s", "a"),
    "core_quality_finding": ("SELECT {columns} FROM core_quality_finding f WHERE f.run_id=%s", "f"),
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _outside_repository(path: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == REPOSITORY_ROOT or REPOSITORY_ROOT in resolved.parents:
        raise CoreImportError(f"Phase 2C {label} must be outside the repository")
    return resolved


def _private_regular_file(path: Path, *, label: str) -> Path:
    resolved = _outside_repository(path, label=label)
    if not resolved.is_file() or resolved.is_symlink() or resolved.stat().st_mode & 0o077:
        raise CoreImportError(f"Phase 2C {label} must be a regular mode-0600 file")
    return resolved


def _load_plan(path: Path) -> dict[str, Any]:
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoreImportError("Phase 2C verification plan is not a readable JSON object") from exc
    if not isinstance(plan, dict):
        raise CoreImportError("Phase 2C verification plan must contain one JSON object")
    validate_import_plan(plan)
    return plan


def _columns(contract: dict[str, Any], *, alias: str) -> str:
    columns = contract.get("columns")
    if not isinstance(columns, list) or not columns or not all(isinstance(value, str) and _IDENTIFIER.fullmatch(value) for value in columns):
        raise CoreImportError("Phase 2C reconciliation contract has unsafe projected columns")
    return ", ".join(f"{alias}.`{column}`" for column in columns)


def collect_observed_rows(connection: Any, plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Read only the plan-bound evidence rows through the Core auditor."""
    contract = plan.get("destination_reconciliation")
    if not isinstance(contract, dict) or set(contract) != set(_TABLES):
        raise CoreImportError("Phase 2C reconciliation plan has an unexpected table contract")
    run_id = str(plan.get("source_run_id") or "")
    if not run_id:
        raise CoreImportError("Phase 2C reconciliation plan lacks a source run ID")
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT DATABASE(), CURRENT_USER()")
        identity = cursor.fetchone()
        if not isinstance(identity, dict) or str(identity.get("DATABASE()") or "") != PRODUCTION_CORE_SCHEMA:
            raise CoreImportError("Core auditor connection did not select the production Core schema")
        if str(identity.get("CURRENT_USER()") or "") != AUDITOR_ACCOUNT:
            raise CoreImportError("Core reconciliation requires the dedicated Core auditor identity")
        observed: dict[str, list[dict[str, Any]]] = {}
        for table, (query, alias) in _TABLES.items():
            cursor.execute(query.format(columns=_columns(contract[table], alias=alias)), (run_id,))
            rows = cursor.fetchall()
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                raise CoreImportError("Core auditor did not return dictionary rows")
            observed[table] = rows
        return observed
    finally:
        cursor.close()


def _new_receipt(path: Path) -> Path:
    resolved = _outside_repository(path, label="verification receipt")
    if resolved.exists() or resolved.is_symlink():
        raise CoreImportError("Refusing to overwrite a Phase 2C verification receipt")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(resolved.parent, 0o700)
    return resolved


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--credential-file", type=Path, required=True, help="0600 provisioned Core-auditor .env file")
    parser.add_argument("--verification-receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt_path = _new_receipt(args.verification_receipt)
    receipt: dict[str, Any] = {"receipt_version": "phase2c-import-verification-v1", "started_at_utc": _utc_now(), "status": "rejected"}
    try:
        plan = _load_plan(_private_regular_file(args.plan, label="import plan"))
        credentials = load_phase2c_credentials(args.credential_file, Phase2CCredentialRole.CORE_AUDITOR)
        receipt.update({"plan_sha256": plan["plan_sha256"], "source_run_id": plan["source_run_id"]})
        connection = mysql.connector.connect(
            host=credentials.host, port=credentials.port, user=credentials.user,
            password=credentials.password, database=PRODUCTION_CORE_SCHEMA, autocommit=False,
        )
        try:
            observed = collect_observed_rows(connection, plan)
        finally:
            connection.close()
        result = reconcile_destination_rows(plan=plan, observed_rows=observed)
        receipt["status"] = "verified" if result["all_match"] else "mismatch"
        receipt["reconciliation"] = result
        receipt["finished_at_utc"] = _utc_now()
        _write_receipt(receipt_path, receipt)
        print(f"PHASE2C RECONCILIATION: status={receipt['status']} receipt={receipt_path}")
        return 0 if result["all_match"] else 2
    except Exception as exc:
        receipt["error_type"] = type(exc).__name__
        receipt["finished_at_utc"] = _utc_now()
        _write_receipt(receipt_path, receipt)
        raise SystemExit(f"PHASE2C RECONCILIATION BLOCKED: {type(exc).__name__}; receipt={receipt_path}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
