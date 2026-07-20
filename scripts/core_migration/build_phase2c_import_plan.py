#!/usr/bin/env python3
"""Build a deterministic Phase 2C import plan from a verified extract package.

This command has no database connection code and cannot perform an import.  It
accepts only the frozen package produced by the dedicated Phase 2C extractor.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.core_migration.mapping import CoreImportError, build_import_plan
from obsidiandroid.core_migration.source_extracts import load_verified_source_extract_package


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "database" / "core_migrations"
FIXTURE_RUN_ID = "20260718T032717Z__a8cf01"


def _file_hash(path: Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def _repository_commit() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        raise RuntimeError("Phase 2C plan creation requires a clean working tree")
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def build_plan_from_package(package_dir: Path, *, repository_commit: str) -> dict:
    """Verify one frozen package then bind it to exact local source identities."""
    manifest, rows = load_verified_source_extract_package(package_dir)
    if manifest["source_run_id"] != FIXTURE_RUN_ID:
        raise CoreImportError(f"Phase 2C planner accepts only fixture {FIXTURE_RUN_ID}")
    if len(rows["analysis_run"]) != 1:
        raise CoreImportError("Phase 2C extract must contain exactly one analysis_run row")
    if len(rows["analysis_snapshot"]) > 1:
        raise CoreImportError("Phase 2C extract must contain at most one analysis_snapshot row")
    if any(str(row.get("run_id") or "") != FIXTURE_RUN_ID for surface_rows in rows.values() for row in surface_rows):
        raise CoreImportError("Phase 2C extract contains a row from another run")
    return build_import_plan(
        run=rows["analysis_run"][0],
        snapshots=rows["analysis_snapshot"],
        samples=rows["analysis_snapshot_sample"],
        artifacts=rows["analysis_artifact"],
        conflicts=rows["snapshot_label_conflict"],
        phase2c_execution_contract={
            "source_extract_manifest_sha256": manifest["extract_manifest_sha256"],
            "repository_commit": repository_commit,
            "migration_checksums": {
                "0001": _file_hash(MIGRATIONS / "0001_core_evidence_foundation.sql"),
                "0002": _file_hash(MIGRATIONS / "0002_core_evidence_contracts.sql"),
            },
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-extract-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Resolve this only after argparse has handled --help.  More importantly,
    # do not accept an operator-supplied commit value: a Phase 2C plan must be
    # bound to the actual clean checkout that created it.
    repository_commit = _repository_commit()
    output = Path(args.output)
    if output.exists():
        raise SystemExit("Refusing to overwrite an existing Phase 2C plan")
    if REPO_ROOT == output.resolve() or REPO_ROOT in output.resolve().parents:
        raise SystemExit("Phase 2C plans must be written outside the repository")
    plan = build_plan_from_package(args.source_extract_dir, repository_commit=repository_commit)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output.chmod(0o600)
    print(f"PLAN ONLY: run_id={plan['source_run_id']} sha256={plan['plan_sha256']} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
