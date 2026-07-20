#!/usr/bin/env python3
"""Offline-only contract check for the preserved Phase 1 review package.

The checker reads versioned design/test files and local generated reports.  It
does not open a database connection or modify files. A passing result means
the historical review package is internally complete; it does not authorize
fixture import or pipeline integration.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts._bootstrap import prepare_script_runtime

ROOT = prepare_script_runtime(__file__)
from obsidiandroid.database import db_config  # noqa: E402

DDL_RELATIVE_PATH = Path("database/core_migrations/0001_core_evidence_foundation.sql")
INVENTORY_RELATIVE_PATH = Path("docs/core_migration/inventory")
FIXTURE_PREVIEW_FILENAME = "july18_fixture_migration_preview.json"
PACKAGE_MANIFEST_FILENAME = "phase1_report_package_manifest.json"
PACKAGE_MANIFEST_CHECKSUM_FILENAME = "phase1_report_package_manifest.sha256"
FIXTURE_RUN_ID = "20260718T032717Z__a8cf01"
LIFECYCLE_TEST_RELATIVE_PATH = Path("tests/test_core_persistence_lifecycle.py")
EXPECTED_FOUNDATION_TABLES = (
    "core_schema_migration", "core_profile", "core_source_snapshot", "core_run", "core_run_sample", "core_artifact", "core_quality_finding",
)
EXPECTED_FIXTURE_ROWS = {
    "core_profile": 1, "core_run": 1, "core_source_snapshot": 1, "core_run_sample": 9716, "core_artifact": 57, "core_quality_finding": 0,
}
REQUIRED_INVENTORY_FILES = (
    "artifact_recoverability_inventory.csv", "core_migration_disposition_matrix.md", "derived_object_inventory.csv",
    "migration_gap_inventory.csv", "preservation_risk_summary.md", "run_evidence_inventory.csv", "warehouse_writer_inventory.csv",
)
REQUIRED_COLUMNS = {
    "derived_object_inventory.csv": {"object_name", "current_writer", "current_readers", "archive_counterpart", "retention_dependency", "artifact_dependency", "regenerability", "proposed_disposition", "report_schema_version"},
    "warehouse_writer_inventory.csv": {"source_file", "function_or_method", "line_or_symbol_reference", "sql_operation", "target_object", "current_connection_provider", "current_database_target", "transaction_start_behavior", "commit_behavior", "rollback_behavior", "retry_behavior", "failure_behavior", "current_readers", "feature_flag_or_enablement_control", "proposed_core_destination", "requires_cutover_flag", "report_schema_version"},
    "artifact_recoverability_inventory.csv": {"artifact_id", "run_id", "ledger_path", "legacy_absolute_path", "run_relative_path", "mutable_pointer_flag", "availability_status", "expected_sha256", "observed_sha256", "hash_validation_status", "archive_recovery_status", "recoverability_confidence", "report_schema_version"},
    "migration_gap_inventory.csv": {"migration_version", "migration_name", "applied_at", "ledger_status", "repository_script_status", "git_history_recovery_status", "local_archive_recovery_status", "Mercury_recovery_status", "intent_status", "resulting_objects_status", "current_schema_preservation_status", "report_schema_version"},
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _foundation_ddl_check(ddl_text: str) -> dict[str, object]:
    missing_tables = [table for table in EXPECTED_FOUNDATION_TABLES if f"CREATE TABLE {table}" not in ddl_text]
    return {
        "ok": bool(ddl_text) and "DESIGN ONLY / PHASE 1" in ddl_text and "do not apply this file to a live database" in ddl_text and not missing_tables,
        "detail": str(DDL_RELATIVE_PATH) if not missing_tables else f"missing tables: {', '.join(missing_tables)}",
    }


def _fixture_preview_check(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"ok": False, "detail": f"missing: {path.name}"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "detail": f"unreadable JSON: {path.name}"}
    classification = payload.get("fixture_classification") or {}
    expected_flags = {"storage_validation_fixture": True, "publication_status": "NOT_APPLICABLE", "frozen_benchmark_status": "not_frozen_benchmark", "paper_reproduction_status": "not_a_paper_reproduction"}
    valid_hash = isinstance(payload.get("plan_sha256"), str) and len(payload["plan_sha256"]) == 64
    ok = payload.get("dry_run") is True and payload.get("run_id") == FIXTURE_RUN_ID and payload.get("proposed_destination_rows") == EXPECTED_FIXTURE_ROWS and classification == expected_flags and valid_hash
    return {"ok": ok, "detail": f"{path.name}: {payload.get('plan_sha256', 'invalid plan hash')}"}


def _csv_contract_check(path: Path, required_columns: set[str]) -> dict[str, object]:
    if not path.is_file():
        return {"ok": False, "detail": f"missing: {path.name}"}
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            header = set(reader.fieldnames or ())
            rows = list(reader)
    except OSError:
        return {"ok": False, "detail": f"unreadable: {path.name}"}
    missing = sorted(required_columns - header)
    return {"ok": not missing and bool(rows), "detail": f"rows={len(rows)}" if not missing else f"missing columns: {', '.join(missing)}", "rows": rows}


def _coverage_check(inventory_dir: Path) -> dict[str, object]:
    derived = _csv_contract_check(inventory_dir / "derived_object_inventory.csv", REQUIRED_COLUMNS["derived_object_inventory.csv"])
    writer = _csv_contract_check(inventory_dir / "warehouse_writer_inventory.csv", REQUIRED_COLUMNS["warehouse_writer_inventory.csv"])
    if not derived["ok"] or not writer["ok"]:
        return {"ok": False, "detail": "derived or writer inventory contract invalid"}
    derived_names = {str(row.get("object_name", "")) for row in derived["rows"]}
    writer_names = {str(row.get("target_object", "")) for row in writer["rows"] if str(row.get("sql_operation", "")).startswith("CREATE_TABLE")}
    missing = sorted(writer_names - derived_names)
    return {"ok": not missing and len(writer_names) == 25, "detail": f"writer_tables={len(writer_names)}; missing={','.join(missing) or 'none'}"}


def _matrix_check(inventory_dir: Path) -> dict[str, object]:
    matrix = inventory_dir / "core_migration_disposition_matrix.md"
    derived = _csv_contract_check(inventory_dir / "derived_object_inventory.csv", REQUIRED_COLUMNS["derived_object_inventory.csv"])
    if not matrix.is_file() or not derived["ok"]:
        return {"ok": False, "detail": "matrix or derived inventory missing"}
    text = matrix.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("|") and not line.startswith("|---")]
    object_rows = rows[1:] if rows else []
    expected = len(derived["rows"])
    return {"ok": len(object_rows) == expected, "detail": f"matrix_object_rows={len(object_rows)}; derived_objects={expected}"}


def _package_manifest_check(inventory_dir: Path) -> dict[str, object]:
    manifest = inventory_dir / PACKAGE_MANIFEST_FILENAME
    sidecar = inventory_dir / PACKAGE_MANIFEST_CHECKSUM_FILENAME
    if not manifest.is_file() or not sidecar.is_file():
        return {"ok": False, "detail": "report package manifest or checksum is missing"}
    expected = f"{_sha256(manifest)}  {manifest.name}"
    actual = sidecar.read_text(encoding="utf-8").strip()
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"ok": False, "detail": "report package manifest is invalid JSON"}
    report_names = {str(item.get("file", "")) for item in payload.get("reports", [])}
    missing = sorted(set(REQUIRED_INVENTORY_FILES) - report_names)
    return {"ok": actual == expected and not missing, "detail": "checksum verified" if actual == expected and not missing else f"missing={','.join(missing) or 'none'}; checksum_match={actual == expected}"}


def evaluate_phase1_closeout(root: Path, *, core_persistence_enabled: bool) -> dict[str, Any]:
    """Evaluate Phase 1 local-report contracts without database access."""
    ddl_path = root / DDL_RELATIVE_PATH
    inventory_dir = root / INVENTORY_RELATIVE_PATH
    ddl_text = ddl_path.read_text(encoding="utf-8") if ddl_path.is_file() else ""
    missing_inventory = [name for name in REQUIRED_INVENTORY_FILES if not (inventory_dir / name).is_file()]
    contract_checks = {name: _csv_contract_check(inventory_dir / name, fields) for name, fields in REQUIRED_COLUMNS.items()}
    checks = {
        "core_persistence_disabled": {"ok": not core_persistence_enabled, "detail": "OBSIDIANDROID_CORE_PERSISTENCE_ENABLED must remain false until separately approved Phase 2C work"},
        "foundation_design_ddl_present": _foundation_ddl_check(ddl_text),
        "generated_inventory_present": {"ok": not missing_inventory, "detail": "all local review reports present" if not missing_inventory else f"missing: {', '.join(missing_inventory)}"},
        "inventory_report_contracts": {"ok": all(bool(check["ok"]) for check in contract_checks.values()), "detail": "; ".join(f"{name}: {check['detail']}" for name, check in contract_checks.items())},
        "writer_created_tables_covered": _coverage_check(inventory_dir),
        "disposition_matrix_coverage": _matrix_check(inventory_dir),
        "generated_report_checksums": _package_manifest_check(inventory_dir),
        "fixture_preview_is_nonpublication_dry_run": _fixture_preview_check(inventory_dir / FIXTURE_PREVIEW_FILENAME),
        "persistence_failure_lifecycle_test_present": {"ok": (root / LIFECYCLE_TEST_RELATIVE_PATH).is_file(), "detail": str(LIFECYCLE_TEST_RELATIVE_PATH)},
    }
    ready = all(bool(item["ok"]) for item in checks.values())
    return {"phase": "phase_1_closeout", "database_accessed": False, "database_writes": False, "foundation_ddl_sha256": hashlib.sha256(ddl_text.encode("utf-8")).hexdigest() if ddl_text else None, "historical_contract_complete": ready, "checks": checks, "next_step": "obtain separate Phase 2C approval" if ready else "resolve the failed Phase 1 check before a new Core action"}


def main() -> int:
    report = evaluate_phase1_closeout(ROOT, core_persistence_enabled=bool(db_config.CORE_PERSISTENCE_ENABLED))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["historical_contract_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
