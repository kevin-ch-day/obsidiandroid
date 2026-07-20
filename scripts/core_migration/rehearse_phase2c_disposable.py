#!/usr/bin/env python3
"""Rehearse one approved Phase 2C plan in an empty disposable Core schema.

This command never creates schemas, grants privileges, reads source schemas,
or accepts the production Core target. An operator must provision a fresh
``od_core_phase2c_rehearsal_*`` schema, apply reviewed migrations, and grant
the writer account access to that schema before invoking it.
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

from obsidiandroid.core_migration.executor import validate_target_name
from obsidiandroid.core_migration.importer import execute_import_plan, validate_import_plan
from obsidiandroid.core_migration.mapping import CoreImportError
from obsidiandroid.core_migration.private_credentials import load_disposable_rehearsal_writer_credentials


REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIRMATION = "REHEARSE_PHASE2C_DISPOSABLE"
_EVIDENCE_TABLES = ("core_profile", "core_source_snapshot", "core_run", "core_run_sample", "core_artifact", "core_quality_finding")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _external_private_file(path: Path, *, label: str, must_exist: bool) -> Path:
    candidate = Path(path).expanduser().resolve()
    try:
        candidate.relative_to(REPO_ROOT)
    except ValueError:
        pass
    else:
        raise CoreImportError(f"Phase 2C rehearsal {label} must be outside the repository")
    if must_exist:
        if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_mode & 0o077:
            raise CoreImportError(f"Phase 2C rehearsal {label} must be a regular mode-0600 file")
    elif candidate.exists():
        raise CoreImportError(f"Refusing to overwrite Phase 2C rehearsal {label}")
    return candidate


def _load_plan(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CoreImportError("Phase 2C rehearsal plan is not a readable JSON object") from exc
    if not isinstance(payload, dict):
        raise CoreImportError("Phase 2C rehearsal plan must contain one JSON object")
    validate_import_plan(payload)
    return payload


def _counts(factory, target: str) -> dict[str, int]:
    connection = factory(target)
    cursor = connection.cursor()
    try:
        counts: dict[str, int] = {}
        for table in _EVIDENCE_TABLES:
            cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            counts[table] = int(cursor.fetchone()[0])
        return counts
    finally:
        cursor.close()
        connection.close()


def _expected_counts(plan: dict[str, Any]) -> dict[str, int]:
    rows = plan["destination_rows"]
    return {table: len(rows[table]) for table in _EVIDENCE_TABLES}


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != _CONFIRMATION:
        raise SystemExit("Phase 2C disposable rehearsal blocked: confirmation token did not match")
    target = validate_target_name(args.target)
    if not target.startswith("od_core_phase2c_rehearsal_"):
        raise SystemExit("Phase 2C disposable rehearsal requires an od_core_phase2c_rehearsal_* target")
    receipt_path = _external_private_file(args.receipt, label="receipt", must_exist=False)
    receipt: dict[str, Any] = {"receipt_version": "phase2c-disposable-rehearsal-v1", "target_database": target, "started_at_utc": _utc_now(), "status": "rejected"}
    try:
        plan = _load_plan(_external_private_file(args.plan, label="plan", must_exist=True))
        credentials = load_disposable_rehearsal_writer_credentials(
            _external_private_file(args.credential_file, label="credential file", must_exist=True),
            target_database=target,
        )

        def factory(database: str):
            return mysql.connector.connect(host=credentials.host, port=credentials.port, user=credentials.user, password=credentials.password, database=database, autocommit=False)

        before = _counts(factory, target)
        if any(before.values()):
            raise CoreImportError("Phase 2C disposable rehearsal target must contain zero evidence rows")
        try:
            execute_import_plan(target_database=target, plan=plan, connection_factory=factory, disposable_failure_checkpoint="after_run_insert")
        except CoreImportError as exc:
            if "Controlled disposable rehearsal failure" not in str(exc):
                raise
        else:
            raise CoreImportError("Controlled rollback probe did not fail")
        after_rollback = _counts(factory, target)
        if after_rollback != before:
            raise CoreImportError("Controlled rollback probe left Core evidence rows in the disposable target")
        imported = execute_import_plan(target_database=target, plan=plan, connection_factory=factory)
        replay = execute_import_plan(target_database=target, plan=plan, connection_factory=factory)
        after_replay = _counts(factory, target)
        expected = _expected_counts(plan)
        if imported.get("status") != "imported" or replay.get("status") != "already_imported" or after_replay != expected:
            raise CoreImportError("Phase 2C disposable rehearsal did not satisfy rollback, import, and replay expectations")
        receipt.update({"status": "passed", "plan_sha256": plan["plan_sha256"], "before_counts": before, "after_rollback_counts": after_rollback, "after_replay_counts": after_replay, "expected_counts": expected, "rollback_checkpoint": "after_run_insert", "initial_import": imported["status"], "replay": replay["status"], "finished_at_utc": _utc_now()})
        _write_receipt(receipt_path, receipt)
        print(f"PHASE2C DISPOSABLE REHEARSAL: status=passed receipt={receipt_path}")
        return 0
    except Exception as exc:
        receipt["error_type"] = type(exc).__name__
        receipt["finished_at_utc"] = _utc_now()
        _write_receipt(receipt_path, receipt)
        raise SystemExit(f"PHASE2C DISPOSABLE REHEARSAL BLOCKED: {type(exc).__name__}; receipt={receipt_path}") from exc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
