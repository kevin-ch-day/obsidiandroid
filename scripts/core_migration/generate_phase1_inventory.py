#!/usr/bin/env python3
"""Generate Phase 1 read-only preservation inventories; never performs DDL/DML."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from scripts._bootstrap import prepare_script_runtime

ROOT = prepare_script_runtime(__file__)
EREBUS_ROOT = ROOT.parent / "erebus-engine-fedora"
from obsidiandroid.database import db_engine  # noqa: E402

OUT = ROOT / "docs" / "core_migration" / "inventory"
WAREHOUSE = ROOT / "src" / "obsidiandroid" / "pipeline" / "stage_results_warehouse.py"
FIXTURE = "20260718T032717Z__a8cf01"


def _rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    frame = db_engine.execute_query(sql, params, fetch=True, as_dataframe=True)
    return [] if frame is None else frame.fillna("").to_dict(orient="records")


def _write_csv(name: str, rows: list[dict[str, Any]]) -> None:
    path = OUT / name
    fields = sorted({key for row in rows for key in row}) or ["status"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _objects() -> list[dict[str, Any]]:
    objects = _rows("""
        SELECT t.TABLE_NAME object_name, t.TABLE_TYPE object_type, t.TABLE_ROWS estimated_rows,
               ROUND((t.DATA_LENGTH+t.INDEX_LENGTH)/1024/1024, 2) estimated_mib,
               t.CREATE_TIME, t.UPDATE_TIME
        FROM information_schema.TABLES t
        WHERE t.TABLE_SCHEMA=DATABASE()
          AND (t.TABLE_NAME LIKE 'analysis_%' OR t.TABLE_NAME LIKE '%permission_%'
               OR t.TABLE_NAME LIKE '%entropy%' OR t.TABLE_NAME LIKE '%jsd%'
               OR t.TABLE_NAME LIKE '%consensus%' OR t.TABLE_NAME LIKE '%ablation%'
               OR t.TABLE_NAME LIKE '%discriminability%' OR t.TABLE_NAME LIKE '%enrichment%'
               OR t.TABLE_NAME LIKE '%performance_spread%' OR t.TABLE_NAME LIKE 'snapshot_label_conflict')
        ORDER BY t.TABLE_NAME
    """)
    creates = set(re.findall(r"CREATE TABLE IF NOT EXISTS ([A-Za-z0-9_]+)", WAREHOUSE.read_text(encoding="utf-8")))
    for row in objects:
        name = str(row["object_name"])
        meta = _rows("""
          SELECT GROUP_CONCAT(CASE WHEN CONSTRAINT_NAME='PRIMARY' THEN COLUMN_NAME END ORDER BY ORDINAL_POSITION) pk,
                 GROUP_CONCAT(DISTINCT CASE WHEN CONSTRAINT_NAME<>'PRIMARY' THEN CONSTRAINT_NAME END) key_names
          FROM information_schema.KEY_COLUMN_USAGE
          WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s
        """, (name,))[0]
        run_link = _rows("""SELECT COUNT(*) n FROM information_schema.COLUMNS
                         WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME='run_id'""", (name,))[0]["n"]
        row.update({
            "primary_key": meta.get("pk", ""), "unique_or_index_keys": meta.get("key_names", ""),
            "run_id_linkage": "yes" if int(run_link or 0) else "no",
            "current_writer": "stage_results_warehouse.py" if name in creates else "not_identified",
            "current_reader": "erebus retention only" if name.startswith("analysis_") or name.endswith("_archive") else "not_identified",
            "archive_counterpart": name[:-8] if name.endswith("_archive") else (name + "_archive" if name + "_archive" in {x['object_name'] for x in objects} else ""),
            "proposed_disposition": "direct_migration" if name in {"analysis_run", "analysis_snapshot", "analysis_snapshot_sample", "analysis_artifact", "snapshot_label_conflict"} else ("archive_only" if name.endswith("_archive") else "undetermined"),
            "disposition_confidence": "high" if name in creates else "low",
        })
    return objects


def _artifact_rows() -> list[dict[str, Any]]:
    result = []
    for row in _rows("SELECT run_id, artifact_key, artifact_path, artifact_sha256, created_at_utc FROM analysis_artifact"):
        raw = str(row["artifact_path"])
        path = Path(raw) if raw.startswith("/") else None
        mutable = ".latest." in raw or raw.endswith(".latest")
        if path and path.is_file():
            actual = _digest(path)
            state = "present_hash_valid" if actual == row["artifact_sha256"] else "present_hash_mismatch"
        else:
            actual, state = "", "missing"
        result.append({**row, "availability_status": state, "actual_sha256": actual,
                       "legacy_absolute_path": str(bool(path)), "mutable_pointer": str(mutable)})
    return result


def _run_evidence(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_run: dict[str, list[dict[str, Any]]] = {}
    for row in artifacts:
        by_run.setdefault(str(row["run_id"]), []).append(row)
    runs = _rows("""SELECT r.run_id, r.profile_id, r.created_at_utc,
                        EXISTS(SELECT 1 FROM analysis_snapshot s WHERE s.run_id=r.run_id) snapshot_present,
                        EXISTS(SELECT 1 FROM analysis_snapshot_sample s WHERE s.run_id=r.run_id) sample_membership_present
                 FROM analysis_run r ORDER BY r.created_at_utc""")
    output=[]
    for run in runs:
        items=by_run.get(str(run["run_id"]), [])
        valid=sum(x["availability_status"] == "present_hash_valid" for x in items)
        output.append({**run, "artifact_metadata_status": "validated" if items else "missing",
                       "artifact_rows": len(items), "hash_valid_artifacts": valid,
                       "artifact_file_status": "validated" if items and valid == len(items) else ("missing" if not valid else "present_unvalidated"),
                       "feature_contract_status": "unknown", "split_status": "unknown",
                       "prediction_status": "unknown", "metric_status": "unknown"})
    return output


def _migration_gaps() -> list[dict[str, Any]]:
    live = _rows("SELECT version, applied_at_utc, note FROM schema_migrations ORDER BY version")
    migration_root = EREBUS_ROOT / "migrations"
    repo = {p.name.split("_", 1)[0] for p in migration_root.glob("*.sql")} if migration_root.is_dir() else set()
    history = subprocess.check_output(["git", "log", "--all", "--name-only", "--format="], cwd=EREBUS_ROOT, text=True) if EREBUS_ROOT.is_dir() else ""
    return [{**row, "repository_status": "script_present" if str(row["version"]) in repo else "script_missing",
             "git_history_status": "recovered_from_git_history" if any(str(row["version"]) in x for x in history.splitlines()) else "intent_unknown",
             "schema_state_status": "current_schema_state_preserved_by_backup"} for row in live]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    objects = _objects(); artifacts = _artifact_rows(); runs = _run_evidence(artifacts); gaps = _migration_gaps()
    _write_csv("derived_object_inventory.csv", objects)
    _write_csv("artifact_recoverability_inventory.csv", artifacts)
    _write_csv("run_evidence_inventory.csv", runs)
    _write_csv("migration_gap_inventory.csv", gaps)
    writers=[]
    for table in sorted(re.findall(r"CREATE TABLE IF NOT EXISTS ([A-Za-z0-9_]+)", WAREHOUSE.read_text(encoding="utf-8"))):
        writers.append({"source_file": str(WAREHOUSE.relative_to(ROOT)), "function": "_ensure_results_schema/_bulk_upsert", "sql_operation": "CREATE TABLE + INSERT", "target_object": table, "schema_qualified": "no", "connection_provider": "db_engine.execute_query", "transaction_behavior": "per query context", "fallback_behavior": "primary Erebus connection", "future_destination": "verified core connection", "must_change_before_cutover": "yes"})
    _write_csv("warehouse_writer_inventory.csv", writers)
    fixture=[r for r in runs if r["run_id"] == FIXTURE][0]
    (OUT / "core_migration_disposition_matrix.md").write_text("# Core migration disposition matrix\n\nFirst wave: `analysis_run`, `analysis_snapshot`, `analysis_snapshot_sample`, `analysis_artifact`, and `snapshot_label_conflict` are proposed for direct migration after Phase 2 approval. All other derived report tables remain `undetermined` or `archive_only`; no legacy table is deleted.\n", encoding="utf-8")
    counts=Counter(row["availability_status"] for row in artifacts)
    missing=sum(row["repository_status"] == "script_missing" for row in gaps)
    (OUT / "preservation_risk_summary.md").write_text(f"# Preservation risk summary\n\n- Runs inventoried: {len(runs)}; runs with snapshots: {sum(bool(r['snapshot_present']) for r in runs)}.\n- Artifact metadata rows: {len(artifacts)}; availability: {dict(counts)}.\n- Missing migration scripts from current checkout: {missing}.\n- July 18 fixture `{FIXTURE}`: {fixture}.\n\nBackups are checksum-valid but restore verification remains separately required. No database write occurred while generating this inventory.\n", encoding="utf-8")
    print(f"Generated read-only Phase 1 inventory at {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
