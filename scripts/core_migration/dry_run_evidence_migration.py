#!/usr/bin/env python3
"""Plan, but never apply, first-wave ObsidianDroid core evidence migration.

The planner reads only the legacy Erebus warehouse and run-local files.  It
emits a deterministic JSON-ready plan for ``analysis_run``, snapshots, sample
membership, artifact metadata, and snapshot conflicts.  It contains no DDL or
DML and is intentionally unsuitable for applying a migration.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from scripts._bootstrap import prepare_script_runtime

prepare_script_runtime(__file__)

from obsidiandroid.database import db_engine  # noqa: E402

FIXTURE_RUN_ID = "20260718T032717Z__a8cf01"
SOURCE_TABLES = (
    "analysis_run",
    "analysis_snapshot",
    "analysis_snapshot_sample",
    "analysis_artifact",
    "snapshot_label_conflict",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_artifact(path_text: str, expected_hash: str | None) -> dict[str, Any]:
    """Classify artifact availability without modifying the referenced file."""
    raw = str(path_text or "")
    mutable = ".latest." in raw or raw.endswith(".latest")
    pointer_kind = "latest_alias" if mutable else "none"
    legacy_absolute = raw.startswith("/") or (len(raw) >= 3 and raw[1:3] == ":\\")
    path = Path(raw) if raw.startswith("/") else None
    exists = bool(path and path.is_file())
    actual_hash = _sha256(path) if exists and path is not None else None
    expected = str(expected_hash or "") or None
    if mutable:
        # A mutable alias may be readable today, but cannot establish immutable
        # run evidence. Retain its observed hash only as diagnostic metadata.
        availability, validation = "mutable_pointer_only", "not_applicable"
        confidence, evidence, notes = "low", "mutable_pointer_only", "mutable .latest alias is not immutable evidence identity"
    elif not raw:
        availability, validation = "unknown", "unknown"
        confidence, evidence, notes = "low", "metadata_only", "artifact ledger path is empty"
    elif path is None:
        availability, validation = "legacy_path_unresolved", "unavailable"
        confidence, evidence, notes = "low", "metadata_only", "non-absolute legacy path was not resolved"
    elif not exists:
        availability, validation = "missing", "unavailable"
        confidence, evidence, notes = "low", "metadata_only", "legacy path is absent at inventory time"
    elif expected and actual_hash == expected:
        availability, validation = "present", "validated"
        confidence, evidence, notes = "high", "validated", "immutable legacy artifact hash validated"
    elif expected:
        availability, validation = "present", "mismatch"
        confidence, evidence, notes = "none", "hash_mismatch", "observed bytes do not match recorded hash"
    else:
        availability, validation = "present", "not_recorded"
        confidence, evidence, notes = "medium", "present_unvalidated", "artifact exists but the ledger has no expected hash"
    return {
        "legacy_source_path": raw,
        "immutable_relative_path": None,
        "availability_status": availability,
        "hash_validation_status": validation,
        "mutable_pointer_flag": mutable,
        "mutable_pointer_kind": pointer_kind,
        "legacy_absolute_path": legacy_absolute,
        "sha256": expected,
        "actual_sha256": actual_hash,
        "byte_size": path.stat().st_size if exists and path is not None else None,
        "file_exists": exists,
        "recoverability_confidence": confidence,
        "evidence_status": evidence,
        "notes": notes,
    }


def build_plan(
    *,
    run: dict[str, Any],
    snapshots: Iterable[dict[str, Any]],
    samples: Iterable[dict[str, Any]],
    artifacts: Iterable[dict[str, Any]],
    conflicts: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic, write-free first-wave migration plan."""
    run_id = str(run["run_id"])
    artifact_rows = []
    for row in sorted(artifacts, key=lambda item: str(item.get("artifact_key", ""))):
        artifact_rows.append(
            {
                "artifact_role": row.get("artifact_key"),
                **classify_artifact(row.get("artifact_path", ""), row.get("artifact_sha256")),
            }
        )
    sample_rows = sorted(samples, key=lambda item: (str(item.get("sha256", "")), int(item.get("sample_id") or 0)))
    snapshot_rows = list(snapshots)
    conflict_rows = list(conflicts)
    completeness = "snapshot_preserved" if snapshot_rows and sample_rows else "ledger_only"
    if artifact_rows and all(row["hash_validation_status"] == "validated" for row in artifact_rows):
        completeness = "artifact_validated" if completeness == "ledger_only" else "snapshot_and_artifact_validated"
    payload = {
        "planner_version": "core-evidence-dry-run-v1",
        "dry_run": True,
        "run_id": run_id,
        "source_tables": list(SOURCE_TABLES),
        "source_run": run,
        "fixture_classification": {
            "storage_validation_fixture": run_id == FIXTURE_RUN_ID,
            "publication_status": "NOT_APPLICABLE" if run_id == FIXTURE_RUN_ID else "unknown",
            "frozen_benchmark_status": "not_frozen_benchmark" if run_id == FIXTURE_RUN_ID else "unknown",
            "paper_reproduction_status": "not_a_paper_reproduction" if run_id == FIXTURE_RUN_ID else "unknown",
        },
        "proposed_destination_rows": {
            "core_profile": 1,
            "core_run": 1,
            "core_source_snapshot": len(snapshot_rows),
            "core_run_sample": len(sample_rows),
            "core_artifact": len(artifact_rows),
            "core_quality_finding": len(conflict_rows),
        },
        "evidence_completeness_status": completeness,
        "artifacts": artifact_rows,
        "validation_expectations": {
            "legacy_run_row_present": True,
            "artifact_rows_preserved": len(artifact_rows),
            "sample_rows_preserved": len(sample_rows),
            "no_source_writes": True,
            "no_core_writes": True,
        },
        "transaction_boundaries": ["core_profile/core_source_snapshot", "core_run", "samples/artifacts/findings"],
        "rollback_strategy": "Phase 2 would delete only destination rows inserted for this run_id; source remains untouched.",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    payload["plan_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def load_legacy_run(run_id: str) -> dict[str, Any]:
    """Read legacy warehouse evidence only; this function never performs DML."""
    def rows(sql: str) -> list[dict[str, Any]]:
        frame = db_engine.execute_query(sql, (run_id,), fetch=True, as_dataframe=True)
        return [] if frame is None else frame.to_dict(orient="records")

    run_rows = rows("SELECT * FROM analysis_run WHERE run_id = %s")
    if len(run_rows) != 1:
        raise ValueError(f"Expected exactly one legacy analysis_run row for {run_id!r}")
    return build_plan(
        run=run_rows[0],
        snapshots=rows("SELECT * FROM analysis_snapshot WHERE run_id = %s"),
        samples=rows("SELECT * FROM analysis_snapshot_sample WHERE run_id = %s"),
        artifacts=rows("SELECT * FROM analysis_artifact WHERE run_id = %s"),
        conflicts=rows("SELECT * FROM snapshot_label_conflict WHERE run_id = %s"),
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Plan first-wave core evidence migration without DB writes.")
    parser.add_argument("--run-id", default=FIXTURE_RUN_ID)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = load_legacy_run(args.run_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"DRY RUN ONLY: wrote plan {args.output} sha256={plan['plan_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
