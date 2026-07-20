#!/usr/bin/env python3
"""Generate read-only Phase 1 Core-migration preservation inventories.

The inventories are a review package, not a migration mechanism.  This module
uses only ``SELECT`` queries against the legacy Erebus schema and filesystem
hashes; it never creates, updates, deletes, or copies production data.
"""

from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from scripts._bootstrap import prepare_script_runtime

ROOT = prepare_script_runtime(__file__)
EREBUS_ROOT = ROOT.parent / "erebus-engine-fedora"
from obsidiandroid.database import db_engine  # noqa: E402
from scripts.core_migration.dry_run_evidence_migration import classify_artifact  # noqa: E402

OUT = ROOT / "docs" / "core_migration" / "inventory"
WAREHOUSE = ROOT / "src" / "obsidiandroid" / "pipeline" / "stage_results_warehouse.py"
FIXTURE = "20260718T032717Z__a8cf01"
REPORT_SCHEMA_VERSION = "phase1-preservation-v2"

DERIVED_FIELDS = (
    "object_name", "object_type", "current_schema", "current_owner", "current_writer", "current_readers",
    "primary_key", "unique_or_index_keys", "estimated_rows", "estimated_mib", "run_id_linkage", "profile_linkage",
    "archive_counterpart", "retention_dependency", "artifact_dependency", "regenerability", "source_of_truth_status",
    "proposed_disposition", "disposition_confidence", "CREATE_TIME", "UPDATE_TIME",
)
WRITER_FIELDS = (
    "source_file", "function_or_method", "line_or_symbol_reference", "sql_operation", "target_object",
    "target_schema_if_qualified", "object_name_qualified_flag", "current_connection_provider", "current_database_target",
    "transaction_start_behavior", "commit_behavior", "rollback_behavior", "retry_behavior", "failure_behavior",
    "exception_propagation", "success_reporting_behavior", "idempotency_behavior", "upsert_behavior", "current_readers",
    "downstream_consumers", "artifact_dependencies", "archive_or_retention_path", "related_views",
    "feature_flag_or_enablement_control", "proposed_core_destination", "migration_disposition", "requires_core_writer",
    "requires_reader_change", "requires_cutover_flag", "requires_backfill", "requires_dual_read_period", "cutover_blocker", "notes",
)
ARTIFACT_FIELDS = (
    "artifact_id", "run_id", "artifact_role", "ledger_path", "legacy_absolute_path", "run_relative_path",
    "mutable_pointer_flag", "mutable_pointer_kind", "file_exists", "availability_status", "expected_sha256",
    "observed_sha256", "hash_validation_status", "expected_size_bytes", "observed_size_bytes", "size_validation_status",
    "media_type", "storage_root_class", "archive_recovery_status", "archive_source", "archive_candidate_path",
    "recoverability_confidence", "evidence_status", "notes", "created_at_utc",
)
MIGRATION_FIELDS = (
    "migration_version", "migration_name", "applied_at", "ledger_status", "repository_script_status",
    "git_history_recovery_status", "local_archive_recovery_status", "Mercury_recovery_status", "recovered_script_path",
    "recovered_script_sha256", "intent_status", "resulting_objects_status", "current_schema_preservation_status",
    "evidence_source", "notes",
)
RUN_FIELDS = (
    "run_id", "profile_id", "created_at_utc", "snapshot_present", "sample_membership_present", "artifact_metadata_status",
    "artifact_rows", "hash_valid_artifacts", "artifact_file_status", "feature_contract_status", "split_status",
    "prediction_status", "metric_status",
)


def _rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    frame = db_engine.execute_query(sql, params, fetch=True, as_dataframe=True)
    return [] if frame is None else frame.fillna("").to_dict(orient="records")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _generator_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _writer_table_lines() -> dict[str, int]:
    """Return every table declared by the active warehouse DDL, with source line."""
    found: dict[str, int] = {}
    pattern = re.compile(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`?([A-Za-z0-9_]+)`?", re.IGNORECASE)
    for line_number, line in enumerate(WAREHOUSE.read_text(encoding="utf-8").splitlines(), start=1):
        match = pattern.search(line)
        if match:
            found[match.group(1)] = line_number
    return found


def _repository_references(object_name: str, *, exclude: Iterable[Path] = ()) -> list[str]:
    """Return actual source references, never reader guesses based on naming."""
    skipped = {path.resolve() for path in exclude}
    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(object_name)}(?![A-Za-z0-9_])")
    matches: list[str] = []
    for base in (ROOT / "src", ROOT / "scripts"):
        for path in base.rglob("*.py"):
            if path.resolve() in skipped:
                continue
            try:
                if pattern.search(path.read_text(encoding="utf-8")):
                    matches.append(str(path.relative_to(ROOT)))
            except OSError:
                continue
    return sorted(matches)


def _metadata(row: dict[str, Any], *, generated_at: str, observed_at: str, commit: str) -> dict[str, Any]:
    return {
        **row,
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "generator_commit": commit,
        "source_database_observed_at_utc": observed_at,
    }


def _write_csv(name: str, rows: list[dict[str, Any]], fields: Iterable[str], *, generated_at: str, observed_at: str, commit: str) -> dict[str, Any]:
    path = OUT / name
    metadata_fields = ("report_schema_version", "generated_at_utc", "generator_commit", "source_database_observed_at_utc")
    fieldnames = [*fields, *metadata_fields]
    materialized = [_metadata(row, generated_at=generated_at, observed_at=observed_at, commit=commit) for row in rows]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(materialized)
    return {"file": name, "row_count": len(materialized), "sha256": _digest(path)}


def _object_disposition(name: str, *, writer_created: bool) -> dict[str, str]:
    foundation = {
        "analysis_run": "core_run",
        "analysis_snapshot": "core_source_snapshot",
        "analysis_snapshot_sample": "core_run_sample",
        "analysis_artifact": "core_artifact",
        "snapshot_label_conflict": "core_quality_finding",
    }
    if name in foundation:
        return {
            "proposed_disposition": "direct_migration", "proposed_core_object": foundation[name],
            "migration_wave": "first_wave_evidence", "transformation_required": "yes: field-level mapping pending Phase 2C",
            "evidence_importance": "high", "blocking_question": "approved Phase 2C mapping and restore receipt required",
            "rationale": "stable run-scoped evidence candidate; source remains untouched",
        }
    if name.endswith("_archive"):
        return {
            "proposed_disposition": "archive_only", "proposed_core_object": "none",
            "migration_wave": "archive_only", "transformation_required": "unknown", "evidence_importance": "historical",
            "blocking_question": "archive retention and recovery policy not approved",
            "rationale": "legacy archive is retained in Erebus; no Core copy is approved",
        }
    return {
        "proposed_disposition": "undetermined", "proposed_core_object": "none",
        "migration_wave": "later_analytical" if writer_created else "undetermined",
        "transformation_required": "unknown", "evidence_importance": "analytical" if writer_created else "unknown",
        "blocking_question": "regenerability and destination not yet approved",
        "rationale": "not a schema-v1 direct-migration candidate",
    }


def _objects() -> list[dict[str, Any]]:
    writer_tables = _writer_table_lines()
    source_text = WAREHOUSE.read_text(encoding="utf-8")
    placeholders = ", ".join(["%s"] * len(writer_tables))
    objects = _rows(
        f"""
        SELECT t.TABLE_NAME object_name, t.TABLE_TYPE object_type, t.TABLE_ROWS estimated_rows,
               ROUND((t.DATA_LENGTH+t.INDEX_LENGTH)/1024/1024, 2) estimated_mib,
               t.CREATE_TIME, t.UPDATE_TIME
        FROM information_schema.TABLES t
        WHERE t.TABLE_SCHEMA=DATABASE()
          AND (t.TABLE_NAME IN ({placeholders}) OR t.TABLE_NAME LIKE 'analysis_%'
               OR t.TABLE_NAME LIKE '%permission_%' OR t.TABLE_NAME LIKE '%entropy%'
               OR t.TABLE_NAME LIKE '%jsd%' OR t.TABLE_NAME LIKE '%consensus%'
               OR t.TABLE_NAME LIKE '%ablation%' OR t.TABLE_NAME LIKE '%discriminability%'
               OR t.TABLE_NAME LIKE '%enrichment%' OR t.TABLE_NAME LIKE '%performance_spread%'
               OR t.TABLE_NAME LIKE 'snapshot_label_conflict')
        ORDER BY t.TABLE_NAME
        """,
        tuple(writer_tables),
    )
    object_names = {str(row["object_name"]) for row in objects}
    for row in objects:
        name = str(row["object_name"])
        meta = _rows(
            """
            SELECT GROUP_CONCAT(CASE WHEN CONSTRAINT_NAME='PRIMARY' THEN COLUMN_NAME END ORDER BY ORDINAL_POSITION) pk,
                   GROUP_CONCAT(DISTINCT CASE WHEN CONSTRAINT_NAME<>'PRIMARY' THEN CONSTRAINT_NAME END) key_names
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s
            """,
            (name,),
        )[0]
        run_link = _rows(
            "SELECT COUNT(*) n FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME='run_id'",
            (name,),
        )[0]["n"]
        profile_link = _rows(
            "SELECT COUNT(*) n FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME='profile_id'",
            (name,),
        )[0]["n"]
        readers = _repository_references(name, exclude=(WAREHOUSE, Path(__file__)))
        disposition = _object_disposition(name, writer_created=name in writer_tables)
        row.update(
            {
                "current_schema": "erebus_threat_intel_prod",
                "current_owner": "ObsidianDroid-derived" if name in writer_tables else "legacy/undetermined",
                "primary_key": meta.get("pk", ""),
                "unique_or_index_keys": meta.get("key_names", ""),
                "run_id_linkage": "yes" if int(run_link or 0) else "no",
                "profile_linkage": "yes" if int(profile_link or 0) else "no",
                "current_writer": "stage_results_warehouse.py" if name in writer_tables else "not_identified",
                "current_readers": ";".join(readers) if readers else "unknown",
                "archive_counterpart": name[:-8] if name.endswith("_archive") else (name + "_archive" if name + "_archive" in object_names else "none"),
                "retention_dependency": "unknown",
                "artifact_dependency": "analysis_artifact" if name != "analysis_artifact" and name in writer_tables else "none",
                "regenerability": "unknown",
                "source_of_truth_status": "derived_obsidiandroid" if name in writer_tables else "unknown",
                "disposition_confidence": "high" if name in {"analysis_run", "analysis_snapshot", "analysis_snapshot_sample", "analysis_artifact", "snapshot_label_conflict"} else "low",
                **disposition,
            }
        )
    return objects


def _artifact_rows() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in _rows("SELECT run_id, artifact_key, artifact_path, artifact_sha256, created_at_utc FROM analysis_artifact"):
        classification = classify_artifact(str(row["artifact_path"]), str(row["artifact_sha256"] or ""))
        result.append(
            {
                "artifact_id": f"{row['run_id']}:{row['artifact_key']}",
                "run_id": row["run_id"],
                "artifact_role": row["artifact_key"],
                "ledger_path": row["artifact_path"],
                "legacy_absolute_path": classification["legacy_absolute_path"],
                "run_relative_path": classification["immutable_relative_path"] or "unknown",
                "mutable_pointer_flag": classification["mutable_pointer_flag"],
                "mutable_pointer_kind": classification["mutable_pointer_kind"],
                "file_exists": classification["file_exists"],
                "availability_status": classification["availability_status"],
                "expected_sha256": classification["sha256"] or "not_recorded",
                "observed_sha256": classification["actual_sha256"] or "unavailable",
                "hash_validation_status": classification["hash_validation_status"],
                "expected_size_bytes": "not_recorded",
                "observed_size_bytes": classification["byte_size"] if classification["byte_size"] is not None else "unavailable",
                "size_validation_status": "not_recorded",
                "media_type": mimetypes.guess_type(str(row["artifact_path"]))[0] or "unknown",
                "storage_root_class": "legacy_absolute_path" if classification["legacy_absolute_path"] else "unresolved_legacy_path",
                "archive_recovery_status": "not_searched",
                "archive_source": "unknown",
                "archive_candidate_path": "unknown",
                "recoverability_confidence": classification["recoverability_confidence"],
                "evidence_status": classification["evidence_status"],
                "notes": classification["notes"],
                "created_at_utc": row["created_at_utc"],
            }
        )
    return result


def _run_evidence(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_run: dict[str, list[dict[str, Any]]] = {}
    for row in artifacts:
        by_run.setdefault(str(row["run_id"]), []).append(row)
    runs = _rows(
        """SELECT r.run_id, r.profile_id, r.created_at_utc,
                  EXISTS(SELECT 1 FROM analysis_snapshot s WHERE s.run_id=r.run_id) snapshot_present,
                  EXISTS(SELECT 1 FROM analysis_snapshot_sample s WHERE s.run_id=r.run_id) sample_membership_present
           FROM analysis_run r ORDER BY r.created_at_utc"""
    )
    output = []
    for run in runs:
        items = by_run.get(str(run["run_id"]), [])
        valid = sum(item["hash_validation_status"] == "validated" and item["availability_status"] == "present" for item in items)
        file_status = "validated" if items and valid == len(items) else ("missing" if not valid else "present_unvalidated")
        output.append(
            {
                **run,
                "artifact_metadata_status": "validated" if items else "missing",
                "artifact_rows": len(items),
                "hash_valid_artifacts": valid,
                "artifact_file_status": file_status,
                "feature_contract_status": "unknown",
                "split_status": "unknown",
                "prediction_status": "unknown",
                "metric_status": "unknown",
            }
        )
    return output


def _migration_gaps() -> list[dict[str, Any]]:
    live = _rows("SELECT version, applied_at_utc, note FROM schema_migrations ORDER BY version")
    migration_root = EREBUS_ROOT / "migrations"
    repo_files = {path.name.split("_", 1)[0]: path for path in migration_root.glob("*.sql")} if migration_root.is_dir() else {}
    history = subprocess.check_output(["git", "log", "--all", "--name-only", "--format="], cwd=EREBUS_ROOT, text=True) if EREBUS_ROOT.is_dir() else ""
    history_paths = set(history.splitlines())
    output = []
    for row in live:
        version = str(row["version"])
        repo_path = repo_files.get(version)
        matching_history = next((path for path in history_paths if re.search(rf"(?:^|/)migrations/{re.escape(version)}(?:_|\\.)", path)), None)
        repository_status = "script_present" if repo_path else "script_missing"
        git_status = "script_present" if repo_path else ("recovered_from_git_history" if matching_history else "script_missing")
        recovered = str(repo_path.relative_to(EREBUS_ROOT)) if repo_path else (matching_history or "")
        output.append(
            {
                "migration_version": version,
                "migration_name": str(row.get("note") or "unknown"),
                "applied_at": row.get("applied_at_utc", ""),
                "ledger_status": "applied",
                "repository_script_status": repository_status,
                "git_history_recovery_status": git_status,
                "local_archive_recovery_status": "not_searched",
                "Mercury_recovery_status": "not_searched",
                "recovered_script_path": recovered,
                "recovered_script_sha256": _digest(repo_path) if repo_path else "unknown",
                "intent_status": "intent_known" if repo_path or matching_history else "intent_unknown",
                "resulting_objects_status": "resulting_objects_unknown",
                "current_schema_preservation_status": "current_schema_state_preserved_by_backup",
                "evidence_source": "schema_migrations;repository_git_history",
                "notes": "No missing SQL or resulting-object relationship is inferred without explicit script evidence.",
            }
        )
    return output


def _writer_rows(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    object_index = {str(row["object_name"]): row for row in objects}
    rows: list[dict[str, Any]] = []
    for table, line in sorted(_writer_table_lines().items()):
        object_row = object_index.get(table, {})
        disposition = _object_disposition(table, writer_created=True)
        common = {
            "source_file": str(WAREHOUSE.relative_to(ROOT)),
            "target_object": table,
            "target_schema_if_qualified": "unqualified",
            "object_name_qualified_flag": "no",
            "current_connection_provider": "db_engine.execute_query",
            "current_database_target": "erebus_threat_intel_prod (default primary connection)",
            "transaction_start_behavior": "database_connection context; connector autocommit=False",
            "commit_behavior": "context commits on successful query completion",
            "rollback_behavior": "context rolls back connector errors",
            "retry_behavior": "unknown",
            "failure_behavior": "exception propagates from warehouse stage",
            "exception_propagation": "yes",
            "success_reporting_behavior": "no dedicated Core success state",
            "current_readers": object_row.get("current_readers", "unknown"),
            "downstream_consumers": object_row.get("current_readers", "unknown"),
            "artifact_dependencies": object_row.get("artifact_dependency", "unknown"),
            "archive_or_retention_path": object_row.get("retention_dependency", "unknown"),
            "related_views": "unknown",
            "feature_flag_or_enablement_control": "none; Core persistence remains disabled and this legacy writer is unchanged",
            "proposed_core_destination": disposition["proposed_core_object"],
            "migration_disposition": disposition["proposed_disposition"],
            "requires_core_writer": "yes" if disposition["proposed_disposition"] == "direct_migration" else "unknown",
            "requires_reader_change": "yes" if disposition["proposed_disposition"] == "direct_migration" else "unknown",
            "requires_cutover_flag": "yes",
            "requires_backfill": "unknown",
            "requires_dual_read_period": "unknown",
            "cutover_blocker": "Phase 2D not approved; Core schema is empty",
            "notes": "Static source evidence only; no live route was changed.",
        }
        rows.append({
            **common, "function_or_method": "_ensure_results_schema", "line_or_symbol_reference": f"{WAREHOUSE.relative_to(ROOT)}:{line}",
            "sql_operation": "CREATE_TABLE_IF_NOT_EXISTS", "idempotency_behavior": "idempotent DDL", "upsert_behavior": "not_applicable",
        })
        rows.append({
            **common, "function_or_method": "_bulk_upsert", "line_or_symbol_reference": f"{WAREHOUSE.relative_to(ROOT)}:1074-1082",
            "sql_operation": "INSERT_ON_DUPLICATE_KEY_UPDATE", "idempotency_behavior": "key-dependent upsert", "upsert_behavior": "ON_DUPLICATE_KEY_UPDATE",
        })
    return rows


def _write_disposition_matrix(objects: list[dict[str, Any]], *, generated_at: str, observed_at: str, commit: str) -> dict[str, Any]:
    path = OUT / "core_migration_disposition_matrix.md"
    columns = (
        "object_name", "object_type", "current_schema", "current_owner", "current_writer", "current_readers", "run_linkage",
        "profile_linkage", "archive_counterpart", "retention_dependency", "artifact_dependency", "regenerability", "evidence_importance",
        "source_of_truth_status", "proposed_core_object", "migration_disposition", "transformation_required", "migration_wave",
        "disposition_confidence", "blocking_question", "rationale",
    )
    lines = [
        "# Core migration disposition matrix",
        "",
        f"- report_schema_version: `{REPORT_SCHEMA_VERSION}`",
        f"- generated_at_utc: `{generated_at}`",
        f"- generator_commit: `{commit}`",
        f"- source_database_observed_at_utc: `{observed_at}`",
        f"- object_rows: `{len(objects)}`",
        "",
        "This is an evidence-conservative planning matrix. `unknown` means the repository and read-only inventory do not establish the value; it is not a migration authorization.",
        "",
        "| " + " | ".join(columns) + " |",
        "|" + "|".join(["---"] * len(columns)) + "|",
    ]
    for row in sorted(objects, key=lambda item: str(item["object_name"])):
        values = [str(row.get(column, "unknown") or "unknown").replace("|", "\\|").replace("\n", " ") for column in columns]
        lines.append("| " + " | ".join(values) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"file": path.name, "row_count": len(objects), "sha256": _digest(path)}


def _write_preservation_summary(runs: list[dict[str, Any]], artifacts: list[dict[str, Any]], gaps: list[dict[str, Any]], fixture: dict[str, Any], *, generated_at: str, observed_at: str, commit: str) -> dict[str, Any]:
    path = OUT / "preservation_risk_summary.md"
    counts = Counter(row["availability_status"] for row in artifacts)
    text = "\n".join(
        [
            "# Preservation risk summary", "",
            f"- report_schema_version: `{REPORT_SCHEMA_VERSION}`", f"- generated_at_utc: `{generated_at}`",
            f"- generator_commit: `{commit}`", f"- source_database_observed_at_utc: `{observed_at}`", "",
            f"- Runs inventoried: {len(runs)}; runs with snapshots: {sum(bool(row['snapshot_present']) for row in runs)}.",
            f"- Artifact metadata rows: {len(artifacts)}; availability: {dict(counts)}.",
            f"- Missing migration scripts from current checkout: {sum(row['repository_script_status'] == 'script_missing' for row in gaps)}.",
            f"- July 18 fixture `{FIXTURE}`: {fixture}.", "",
            "Backups are checksum-valid but restore verification remains separately required. This generator used read-only database queries and did not write, copy, or alter production evidence.",
        ]
    )
    path.write_text(text + "\n", encoding="utf-8")
    return {"file": path.name, "row_count": 4, "sha256": _digest(path)}


def _write_manifest(reports: list[dict[str, Any]], *, generated_at: str, observed_at: str, commit: str) -> None:
    path = OUT / "phase1_report_package_manifest.json"
    payload = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "generator_commit": commit,
        "source_database_observed_at_utc": observed_at,
        "reports": reports,
        "generator_mode": "read_only_database_and_filesystem_inventory",
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "phase1_report_package_manifest.sha256").write_text(f"{_digest(path)}  {path.name}\n", encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    generated_at = _utc_now()
    observed_at = generated_at
    commit = _generator_commit()
    objects = _objects()
    artifacts = _artifact_rows()
    runs = _run_evidence(artifacts)
    gaps = _migration_gaps()
    writers = _writer_rows(objects)
    reports = [
        _write_csv("derived_object_inventory.csv", objects, DERIVED_FIELDS, generated_at=generated_at, observed_at=observed_at, commit=commit),
        _write_csv("warehouse_writer_inventory.csv", writers, WRITER_FIELDS, generated_at=generated_at, observed_at=observed_at, commit=commit),
        _write_csv("run_evidence_inventory.csv", runs, RUN_FIELDS, generated_at=generated_at, observed_at=observed_at, commit=commit),
        _write_csv("artifact_recoverability_inventory.csv", artifacts, ARTIFACT_FIELDS, generated_at=generated_at, observed_at=observed_at, commit=commit),
        _write_csv("migration_gap_inventory.csv", gaps, MIGRATION_FIELDS, generated_at=generated_at, observed_at=observed_at, commit=commit),
        _write_disposition_matrix(objects, generated_at=generated_at, observed_at=observed_at, commit=commit),
    ]
    fixture = next(row for row in runs if row["run_id"] == FIXTURE)
    reports.append(_write_preservation_summary(runs, artifacts, gaps, fixture, generated_at=generated_at, observed_at=observed_at, commit=commit))
    _write_manifest(reports, generated_at=generated_at, observed_at=observed_at, commit=commit)
    print(f"Generated {len(reports)} read-only Phase 1 reports at {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
