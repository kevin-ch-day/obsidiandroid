#!/usr/bin/env python3
"""Check whether the local Phase 1 Core-migration review package is complete.

This command is deliberately offline-only: it reads versioned design files,
the local generated inventory directory, and the already-loaded feature flag.
It never creates a database connection, performs SQL, or changes any file.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from scripts._bootstrap import prepare_script_runtime

ROOT = prepare_script_runtime(__file__)

from obsidiandroid.database import db_config  # noqa: E402

DDL_RELATIVE_PATH = Path("database/core_migrations/0001_core_evidence_foundation.sql")
INVENTORY_RELATIVE_PATH = Path("docs/core_migration/inventory")
FIXTURE_PREVIEW_FILENAME = "july18_fixture_migration_preview.json"
FIXTURE_RUN_ID = "20260718T032717Z__a8cf01"
EXPECTED_FOUNDATION_TABLES = (
    "core_schema_migration",
    "core_profile",
    "core_source_snapshot",
    "core_run",
    "core_run_sample",
    "core_artifact",
    "core_quality_finding",
)
EXPECTED_FIXTURE_ROWS = {
    "core_profile": 1,
    "core_run": 1,
    "core_source_snapshot": 1,
    "core_run_sample": 9716,
    "core_artifact": 57,
    "core_quality_finding": 0,
}
REQUIRED_INVENTORY_FILES = (
    "artifact_recoverability_inventory.csv",
    "core_migration_disposition_matrix.md",
    "derived_object_inventory.csv",
    "migration_gap_inventory.csv",
    "preservation_risk_summary.md",
    "run_evidence_inventory.csv",
    "warehouse_writer_inventory.csv",
)


def _foundation_ddl_check(ddl_text: str) -> dict[str, object]:
    """Validate the reviewed, design-only evidence-table foundation."""
    missing_tables = [table for table in EXPECTED_FOUNDATION_TABLES if f"CREATE TABLE {table}" not in ddl_text]
    ok = (
        bool(ddl_text)
        and "DESIGN ONLY / PHASE 1" in ddl_text
        and "do not apply this file to a live database" in ddl_text
        and not missing_tables
    )
    return {
        "ok": ok,
        "detail": str(DDL_RELATIVE_PATH) if not missing_tables else f"missing tables: {', '.join(missing_tables)}",
    }


def _fixture_preview_check(path: Path) -> dict[str, object]:
    """Validate the local, nonpublication July 18 storage-fixture preview."""
    if not path.is_file():
        return {"ok": False, "detail": f"missing: {path.name}"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "detail": f"unreadable JSON: {path.name}"}
    classification = payload.get("fixture_classification") or {}
    expected_flags = {
        "storage_validation_fixture": True,
        "publication_status": "NOT_APPLICABLE",
        "frozen_benchmark_status": "not_frozen_benchmark",
        "paper_reproduction_status": "not_a_paper_reproduction",
    }
    valid_hash = isinstance(payload.get("plan_sha256"), str) and len(payload["plan_sha256"]) == 64
    ok = (
        payload.get("dry_run") is True
        and payload.get("run_id") == FIXTURE_RUN_ID
        and payload.get("proposed_destination_rows") == EXPECTED_FIXTURE_ROWS
        and classification == expected_flags
        and valid_hash
    )
    return {
        "ok": ok,
        "detail": f"{path.name}: {payload.get('plan_sha256', 'invalid plan hash')}",
    }


def evaluate_phase1_closeout(root: Path, *, core_persistence_enabled: bool) -> dict[str, Any]:
    """Evaluate static Phase 1 stop conditions without accessing any database."""
    ddl_path = root / DDL_RELATIVE_PATH
    inventory_dir = root / INVENTORY_RELATIVE_PATH
    ddl_text = ddl_path.read_text(encoding="utf-8") if ddl_path.is_file() else ""
    missing_inventory = [name for name in REQUIRED_INVENTORY_FILES if not (inventory_dir / name).is_file()]
    checks = {
        "core_persistence_disabled": {
            "ok": not core_persistence_enabled,
            "detail": "OBSIDIANDROID_CORE_PERSISTENCE_ENABLED must remain false in Phase 1",
        },
        "foundation_ddl_present_and_unapplied": _foundation_ddl_check(ddl_text),
        "generated_inventory_present": {
            "ok": not missing_inventory,
            "detail": "all local review reports present" if not missing_inventory else f"missing: {', '.join(missing_inventory)}",
        },
        "fixture_preview_is_nonpublication_dry_run": _fixture_preview_check(inventory_dir / FIXTURE_PREVIEW_FILENAME),
    }
    ready = all(bool(item["ok"]) for item in checks.values())
    return {
        "phase": "phase_1_closeout",
        "database_accessed": False,
        "database_writes": False,
        "foundation_ddl_sha256": hashlib.sha256(ddl_text.encode("utf-8")).hexdigest() if ddl_text else None,
        "ready_for_human_phase2_review": ready,
        "checks": checks,
        "next_step": "obtain separate Phase 2 approval" if ready else "resolve the failed Phase 1 check; do not begin Phase 2",
    }


def main() -> int:
    report = evaluate_phase1_closeout(ROOT, core_persistence_enabled=bool(db_config.CORE_PERSISTENCE_ENABLED))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready_for_human_phase2_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
