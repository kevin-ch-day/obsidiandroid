#!/usr/bin/env python3
"""Create and retain one explicitly named Phase 2B disposable Core schema.

This is the only Phase 2B script that performs DDL/DML.  It has no source
reader, refuses production names, and uses synthetic records only.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
import shutil
import tempfile
from typing import Any

import mysql.connector

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.core_migration.executor import apply_migrations, validate_target_name
from obsidiandroid.core_migration.importer import execute_import_plan
from obsidiandroid.core_migration.mapping import build_import_plan


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "database" / "core_migrations"
_SKIP_PARTS = {".git", ".venv", "output", "__pycache__", ".pytest_cache"}


def _utc_target() -> str:
    return "od_core_phase2b_validate_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _contains_target_reference(target: str) -> bool:
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or any(part in _SKIP_PARTS for part in path.parts):
            continue
        try:
            if target in path.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            continue
    return False


def _connect(socket: str, option_file: Path, database: str | None = None):
    """Use a local client option file; no credential is accepted or emitted here."""
    kwargs: dict[str, Any] = {"option_files": str(option_file), "unix_socket": socket, "autocommit": False}
    if database:
        kwargs["database"] = database
    return mysql.connector.connect(**kwargs)


def _execute(cursor, sql: str, params: tuple[Any, ...] = ()) -> None:
    cursor.execute(sql, params)


def _synthetic_plan() -> dict[str, Any]:
    return build_import_plan(
        run={
            "run_id": "phase2b-synthetic-run",
            "profile_id": "phase2b-synthetic-profile",
            "created_at_utc": "2026-07-19 00:00:00",
            "git_commit": "0" * 40,
            "selection_rule_version": "synthetic-v1",
            "snapshot_sha256_hash": "a" * 64,
        },
        snapshots=[{
            "run_id": "phase2b-synthetic-run", "extracted_at_utc": "2026-07-19 00:00:00",
            "selection_rule_version": "synthetic-v1", "snapshot_sha256_hash": "a" * 64,
            "snapshot_row_count": 1, "selected_vendor_count": 0, "included_vendor_count": 0,
            "excluded_vendor_count": 0, "vendor_constrained_run_flag": 0,
        }],
        samples=[{
            "run_id": "phase2b-synthetic-run", "sha256": "b" * 64, "sample_id": 7,
            "family_canonical": "synthetic_family", "type_slug": "synthetic_type",
            "extracted_at_utc": "2026-07-19 00:00:00", "feature_hash": "c" * 64,
        }],
        artifacts=[{
            "run_id": "phase2b-synthetic-run", "artifact_key": "missing_artifact",
            "artifact_path": "/synthetic/absent.csv", "artifact_sha256": "d" * 64,
            "created_at_utc": "2026-07-19 00:00:00",
        }],
        conflicts=[{
            "run_id": "phase2b-synthetic-run", "sha256": "b" * 64,
            "conflict_type": "synthetic_label_conflict", "observed_values": "one|two",
            "created_at_utc": "2026-07-19 00:00:00",
        }],
    )


def _validate_synthetic_states(factory, target: str) -> dict[str, Any]:
    connection = factory(target)
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT source_snapshot_id FROM core_source_snapshot LIMIT 1")
        snapshot_id = cursor.fetchone()[0]
        cursor.execute("SELECT source_record_hash FROM core_quality_finding LIMIT 1")
        finding_hash = cursor.fetchone()[0]
        synthetic_roles = (
            ("mutable_artifact", "/synthetic/report.latest.csv", "mutable_pointer_only", "not_applicable", 1, "latest_alias", None),
            ("validated_artifact", "runs/synthetic/validated.csv", "present", "validated", 0, "none", "e" * 64),
            ("mismatch_artifact", "runs/synthetic/mismatch.csv", "present", "mismatch", 0, "none", "0" * 64),
        )
        for role, path, availability, hash_state, flag, kind, observed in synthetic_roles:
            _execute(cursor, "INSERT INTO core_artifact (run_id, artifact_role, source_snapshot_id, immutable_relative_path, legacy_source_path, availability_status, hash_validation_status, mutable_pointer_flag, mutable_pointer_kind, retention_status, storage_root_class, archive_recovery_status, recoverability_confidence, evidence_status, expected_sha256, observed_sha256, imported_at_utc) VALUES (%s,%s,%s,%s,NULL,%s,%s,%s,%s,'synthetic','synthetic','unknown','unknown','synthetic',%s,%s,UTC_TIMESTAMP(6))", ("phase2b-synthetic-run", role, snapshot_id, path, availability, hash_state, flag, kind, "e" * 64 if role == "validated_artifact" else "f" * 64 if role == "mismatch_artifact" else None, observed))
        connection.commit()
        invalid_rejected = False
        try:
            _execute(cursor, "UPDATE core_run SET run_status = 'invalid_state' WHERE run_id = %s", ("phase2b-synthetic-run",))
            connection.commit()
        except Exception:
            connection.rollback()
            invalid_rejected = True
        delete_rejected = False
        try:
            _execute(cursor, "DELETE FROM core_run WHERE run_id = %s", ("phase2b-synthetic-run",))
            connection.commit()
        except Exception:
            connection.rollback()
            delete_rejected = True
        contradictory_run_rejections = 0
        contradictory_runs = (
            ("ledger-with-snapshot", "ledger_only", snapshot_id, "ledger_only", None),
            ("snapshot-without-snapshot", "snapshot_backed", None, "snapshot_backed", None),
            ("self-supersession", "ledger_only", None, "ledger_only", "self-supersession"),
        )
        for run_id, kind, linked_snapshot, evidence, supersedes in contradictory_runs:
            try:
                _execute(cursor, "INSERT INTO core_run (run_id, profile_id, source_snapshot_id, run_kind, run_status, scope_kind, publication_applicability, evidence_completeness_status, imported_at_utc, supersedes_run_id) VALUES (%s,'phase2b-synthetic-profile',%s,%s,'planned','synthetic','not_applicable',%s,UTC_TIMESTAMP(6),%s)", (run_id, linked_snapshot, kind, evidence, supersedes))
                connection.commit()
            except Exception:
                connection.rollback()
                contradictory_run_rejections += 1
        artifact_rule_rejections = 0
        invalid_artifacts = (
            ("bad-pointer", "present", "unavailable", 1, "latest_alias", None, None),
            ("bad-validated", "present", "validated", 0, "none", "1" * 64, None),
            ("bad-mismatch", "present", "mismatch", 0, "none", "2" * 64, "2" * 64),
        )
        for role, availability, hash_state, pointer, pointer_kind, expected, observed in invalid_artifacts:
            try:
                _execute(cursor, "INSERT INTO core_artifact (run_id,artifact_role,source_snapshot_id,availability_status,hash_validation_status,mutable_pointer_flag,mutable_pointer_kind,retention_status,storage_root_class,archive_recovery_status,recoverability_confidence,evidence_status,expected_sha256,observed_sha256,imported_at_utc) VALUES ('phase2b-synthetic-run',%s,%s,%s,%s,%s,%s,'synthetic','synthetic','unknown','unknown','synthetic',%s,%s,UTC_TIMESTAMP(6))", (role, snapshot_id, availability, hash_state, pointer, pointer_kind, expected, observed))
                connection.commit()
            except Exception:
                connection.rollback()
                artifact_rule_rejections += 1
        duplicate_finding_rejected = False
        try:
            _execute(cursor, "INSERT INTO core_quality_finding (run_id,source_snapshot_id,finding_code,finding_kind,severity,category,message,resolution_status,source_record_hash,created_at_utc) VALUES ('phase2b-synthetic-run',%s,'duplicate','source_conflict','medium','snapshot_label','duplicate source row','open',%s,UTC_TIMESTAMP(6))", (snapshot_id, finding_hash))
            connection.commit()
        except Exception:
            connection.rollback()
            duplicate_finding_rejected = True
        # Valid ledger-only evidence is a required independent state.
        _execute(cursor, "INSERT INTO core_run (run_id, profile_id, run_kind, run_status, scope_kind, publication_applicability, evidence_completeness_status, imported_at_utc) VALUES ('ledger-only-valid','phase2b-synthetic-profile','ledger_only','planned','synthetic','not_applicable','ledger_only',UTC_TIMESTAMP(6))")
        connection.commit()
        cursor.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'")
        table_count = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = DATABASE() AND UNIQUE_CONSTRAINT_SCHEMA <> DATABASE()")
        cross_schema_fks = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT migration_version, receipt_id FROM core_schema_migration "
            "WHERE execution_status='applied' ORDER BY migration_version"
        )
        ledger_rows = cursor.fetchall()
        ledger_versions = [str(version) for version, _receipt in ledger_rows]
        ledger_receipt_ids = [str(receipt) for _version, receipt in ledger_rows if receipt is not None]
        cursor.execute("SELECT artifact_role, availability_status, hash_validation_status FROM core_artifact ORDER BY artifact_role")
        artifacts = cursor.fetchall()
        return {
            "table_count": table_count,
            "cross_schema_foreign_keys": cross_schema_fks,
            "ledger_versions": ledger_versions,
            "ledger_receipt_ids_unique": len(ledger_receipt_ids) == len(set(ledger_receipt_ids)),
            "invalid_status_rejected": invalid_rejected,
            "run_delete_rejected": delete_rejected,
            "contradictory_run_rejections": contradictory_run_rejections,
            "artifact_rule_rejections": artifact_rule_rejections,
            "duplicate_finding_rejected": duplicate_finding_rejected,
            "artifact_states": artifacts,
        }
    finally:
        cursor.close()
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=_utc_target())
    parser.add_argument("--unix-socket", default="/var/lib/mysql/mysql.sock")
    parser.add_argument("--option-file", type=Path, default=Path.home() / ".my.cnf")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    target = validate_target_name(args.target)
    print(f"PROPOSED DISPOSABLE CORE SCHEMA: {target}")
    if _contains_target_reference(target):
        raise SystemExit("Refusing: target appears in repository/application configuration")
    if not args.option_file.is_file():
        raise SystemExit("Refusing: local MariaDB option file is unavailable")
    admin = _connect(args.unix_socket, args.option_file)
    cursor = admin.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s", (target,))
        if int(cursor.fetchone()[0]):
            raise SystemExit("Refusing: disposable target already exists")
        cursor.execute(f"CREATE DATABASE `{target}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        admin.commit()
    finally:
        cursor.close()
        admin.close()

    factory = lambda database: _connect(args.unix_socket, args.option_file, database)
    receipt = apply_migrations(target_database=target, migrations_dir=MIGRATIONS, connection_factory=factory, application_commit=None, dry_run=False, receipt_path=args.receipt)
    plan = _synthetic_plan()
    imported = execute_import_plan(target_database=target, plan=plan, connection_factory=factory)
    idempotent = execute_import_plan(target_database=target, plan=plan, connection_factory=factory)
    validation = _validate_synthetic_states(factory, target)
    rerun = apply_migrations(target_database=target, migrations_dir=MIGRATIONS, connection_factory=factory, application_commit=None, dry_run=False)
    checksum_mismatch_rejected = False
    failed_migration_not_ledgered = False
    with tempfile.TemporaryDirectory(prefix="od-core-phase2b-") as temp_dir:
        altered = Path(temp_dir) / "migrations"
        shutil.copytree(MIGRATIONS, altered)
        (altered / "0002_core_evidence_contracts.sql").write_text(
            (altered / "0002_core_evidence_contracts.sql").read_text(encoding="utf-8")
            + "\n-- altered only for checksum validation\n",
            encoding="utf-8",
        )
        try:
            apply_migrations(target_database=target, migrations_dir=altered, connection_factory=factory, dry_run=False)
        except Exception:
            checksum_mismatch_rejected = True
        (altered / "0002_core_evidence_contracts.sql").write_text(
            (MIGRATIONS / "0002_core_evidence_contracts.sql").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        # Use the next free version so the failure probe does not collide with
        # committed Phase 2D migrations 0003-0005.
        (altered / "0006_intentionally_broken.sql").write_text("THIS IS NOT VALID SQL;", encoding="utf-8")
        try:
            apply_migrations(target_database=target, migrations_dir=altered, connection_factory=factory, dry_run=False)
        except Exception:
            check = factory(target)
            check_cursor = check.cursor()
            try:
                check_cursor.execute(
                    "SELECT COUNT(*) FROM core_schema_migration "
                    "WHERE migration_version = '0006' AND execution_status = 'applied'"
                )
                failed_migration_not_ledgered = int(check_cursor.fetchone()[0]) == 0
            finally:
                check_cursor.close()
                check.close()
    result = {"schema": target, "migration": receipt, "import": imported, "idempotent_import": idempotent, "reexecution": rerun, "validation": validation}
    args.receipt.with_name(args.receipt.stem + "_validation.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    assert validation["table_count"] == 19
    assert validation["cross_schema_foreign_keys"] == 0
    assert validation["ledger_versions"] == ["0001", "0002", "0003", "0004", "0005"]
    assert validation["ledger_receipt_ids_unique"] is True
    assert validation["invalid_status_rejected"] and validation["run_delete_rejected"]
    assert validation["contradictory_run_rejections"] == 3
    assert validation["artifact_rule_rejections"] == 3
    assert validation["duplicate_finding_rejected"]
    assert idempotent["status"] == "already_imported"
    assert rerun["status"] == "applied" and rerun["skipped"] == ["0001", "0002", "0003", "0004", "0005"]
    assert len(set(receipt["migration_receipt_ids"].values())) == len(receipt["migration_receipt_ids"])
    assert checksum_mismatch_rejected and failed_migration_not_ledgered
    print(json.dumps({
        "schema": target,
        "table_count": validation["table_count"],
        "import": imported["status"],
        "idempotent_import": idempotent["status"],
        "migration_reexecution": rerun["skipped"],
        "ledger_receipt_ids_unique": validation["ledger_receipt_ids_unique"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
