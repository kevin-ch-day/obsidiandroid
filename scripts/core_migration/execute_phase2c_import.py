#!/usr/bin/env python3
"""Execute one separately approved Phase 2C Core fixture import.

This is deliberately not part of ``run.sh`` or the normal pipeline. It never
reads an upstream source database: it accepts only an already-verified import
plan, a separately reviewed single-use authorization, and two preflight
reports. The command refuses to run without an explicit operator confirmation
and writes its receipt outside the repository.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any

import mysql.connector

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.core_migration.authorization import (
    FileAuthorizationConsumptionLedger,
    Phase2CImportAuthorization,
    PRODUCTION_CORE_SCHEMA,
    require_clean_repository_at_commit,
    validate_core_preflight_payload,
    validate_host_preflight_payload,
)
from obsidiandroid.core_migration.importer import execute_import_plan, validate_import_plan
from obsidiandroid.core_migration.mapping import CoreImportError
from obsidiandroid.core_migration.private_credentials import Phase2CCredentialRole, load_phase2c_credentials


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CONFIRMATION = "EXECUTE_APPROVED_PHASE2C_IMPORT"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _outside_repository(path: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == REPOSITORY_ROOT or REPOSITORY_ROOT in resolved.parents:
        raise CoreImportError(f"Phase 2C {label} must be outside the repository")
    return resolved


def _private_regular_file(path: Path, *, label: str) -> Path:
    resolved = _outside_repository(path, label=label)
    if not resolved.is_file() or resolved.is_symlink():
        raise CoreImportError(f"Phase 2C {label} must be a regular file")
    if resolved.stat().st_mode & 0o077:
        raise CoreImportError(f"Phase 2C {label} must be mode 0600")
    return resolved


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoreImportError(f"Phase 2C {label} is not a readable JSON object") from exc
    if not isinstance(payload, dict):
        raise CoreImportError(f"Phase 2C {label} must contain one JSON object")
    return payload


def _authorization_from_payload(payload: dict[str, Any]) -> Phase2CImportAuthorization:
    expected = set(Phase2CImportAuthorization.__dataclass_fields__)
    if set(payload) != expected:
        raise CoreImportError("Phase 2C authorization has missing or unrecognized fields")
    try:
        return Phase2CImportAuthorization(**payload)
    except TypeError as exc:
        raise CoreImportError("Phase 2C authorization has an invalid field shape") from exc


def _new_private_receipt(path: Path) -> Path:
    resolved = _outside_repository(path, label="execution receipt")
    if resolved.exists() or resolved.is_symlink():
        raise CoreImportError("Refusing to overwrite a Phase 2C execution receipt")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(resolved.parent, 0o700)
    return resolved


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True, help="Reviewed deterministic plan outside the repository")
    parser.add_argument("--authorization", type=Path, required=True, help="Reviewed single-use authorization outside the repository")
    parser.add_argument("--core-preflight", type=Path, required=True, help="Reviewed Core audit JSON outside the repository")
    parser.add_argument("--host-preflight", type=Path, required=True, help="Reviewed host preflight JSON outside the repository")
    parser.add_argument("--credential-file", type=Path, required=True, help="0600 provisioned Core-writer .env file")
    parser.add_argument("--consumption-ledger-dir", type=Path, required=True, help="Private external single-use receipt directory")
    parser.add_argument("--execution-receipt", type=Path, required=True, help="New private external execution receipt")
    parser.add_argument("--confirm", required=True, help=f"Exact confirmation token: {_CONFIRMATION}")
    args = parser.parse_args()
    if args.confirm != _CONFIRMATION:
        raise SystemExit("Phase 2C import blocked: explicit confirmation token did not match")

    receipt_path = _new_private_receipt(args.execution_receipt)
    receipt: dict[str, Any] = {
        "receipt_version": "phase2c-import-execution-v1",
        "started_at_utc": _utc_now(),
        "status": "rejected",
        "target_database": PRODUCTION_CORE_SCHEMA,
    }
    try:
        plan_path = _private_regular_file(args.plan, label="import plan")
        authorization_path = _private_regular_file(args.authorization, label="authorization")
        core_preflight_path = _private_regular_file(args.core_preflight, label="Core preflight")
        host_preflight_path = _private_regular_file(args.host_preflight, label="host preflight")
        ledger_dir = _outside_repository(args.consumption_ledger_dir, label="authorization ledger")
        plan = _load_json_object(plan_path, label="import plan")
        authorization = _authorization_from_payload(_load_json_object(authorization_path, label="authorization"))
        core_preflight = _load_json_object(core_preflight_path, label="Core preflight")
        host_preflight = _load_json_object(host_preflight_path, label="host preflight")
        # Repeat the importer gates before loading any writer secret. The
        # importer repeats them immediately before its one-time consumption.
        validate_import_plan(plan)
        authorization.validate_for(target_database=PRODUCTION_CORE_SCHEMA, plan=plan)
        validate_core_preflight_payload(core_preflight, authorization)
        validate_host_preflight_payload(host_preflight, authorization)
        require_clean_repository_at_commit(REPOSITORY_ROOT, authorization.repository_commit)
        if (ledger_dir / f"{authorization.authorization_id}.consumed.json").exists():
            raise CoreImportError("Phase 2C authorization has already been consumed")
        credentials = load_phase2c_credentials(args.credential_file, Phase2CCredentialRole.CORE_WRITER)
        receipt.update({
            "authorization_id": authorization.authorization_id,
            "plan_sha256": str(plan.get("plan_sha256") or ""),
            "source_run_id": str(plan.get("source_run_id") or ""),
        })

        def connection_factory(target: str):
            return mysql.connector.connect(
                host=credentials.host, port=credentials.port, user=credentials.user,
                password=credentials.password, database=target, autocommit=False,
            )

        result = execute_import_plan(
            target_database=PRODUCTION_CORE_SCHEMA,
            plan=plan,
            connection_factory=connection_factory,
            production_authorization=authorization,
            authorization_consumption_ledger=FileAuthorizationConsumptionLedger(ledger_dir),
            production_core_preflight=core_preflight,
            production_host_preflight=host_preflight,
        )
        receipt["status"] = str(result.get("status") or "unknown")
        receipt["result"] = result
        receipt["finished_at_utc"] = _utc_now()
        _write_receipt(receipt_path, receipt)
        print(f"PHASE2C IMPORT: status={receipt['status']} receipt={receipt_path}")
        return 0
    except Exception as exc:
        receipt["error_type"] = type(exc).__name__
        if isinstance(exc, mysql.connector.Error) and getattr(exc, "errno", None) is not None:
            receipt["database_error_code"] = int(exc.errno)
        receipt["finished_at_utc"] = _utc_now()
        _write_receipt(receipt_path, receipt)
        raise SystemExit(f"PHASE2C IMPORT BLOCKED: {type(exc).__name__}; receipt={receipt_path}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
