#!/usr/bin/env python3
"""Check whether the local Phase 1 Core-migration review package is complete.

This command is deliberately offline-only: it reads versioned design files,
the local generated inventory directory, and the already-loaded feature flag.
It never creates a database connection, performs SQL, or changes any file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts._bootstrap import prepare_script_runtime

ROOT = prepare_script_runtime(__file__)

from obsidiandroid.database import db_config  # noqa: E402

DDL_RELATIVE_PATH = Path("database/core_migrations/0001_core_evidence_foundation.sql")
INVENTORY_RELATIVE_PATH = Path("docs/core_migration/inventory")
REQUIRED_INVENTORY_FILES = (
    "artifact_recoverability_inventory.csv",
    "core_migration_disposition_matrix.md",
    "derived_object_inventory.csv",
    "migration_gap_inventory.csv",
    "preservation_risk_summary.md",
    "run_evidence_inventory.csv",
    "warehouse_writer_inventory.csv",
)


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
        "foundation_ddl_present_and_unapplied": {
            "ok": bool(ddl_text)
            and "DESIGN ONLY / PHASE 1" in ddl_text
            and "do not apply this file to a live database" in ddl_text,
            "detail": str(DDL_RELATIVE_PATH),
        },
        "generated_inventory_present": {
            "ok": not missing_inventory,
            "detail": "all local review reports present" if not missing_inventory else f"missing: {', '.join(missing_inventory)}",
        },
    }
    ready = all(bool(item["ok"]) for item in checks.values())
    return {
        "phase": "phase_1_closeout",
        "database_accessed": False,
        "database_writes": False,
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
