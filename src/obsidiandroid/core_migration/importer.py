"""Synthetic/testable Core import executor; not connected to the normal pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any, Callable

from .authorization import Phase2CImportAuthorization, PRODUCTION_CORE_SCHEMA
from .executor import CoreMigrationError, validate_target_name
from .mapping import CoreImportError


_RUN_EVIDENCE_BY_KIND = {
    "ledger_only": {"ledger_only", "incomplete", "persistence_disabled", "persistence_failed", "import_rejected", "superseded"},
    "snapshot_backed": {"snapshot_backed", "incomplete", "persistence_disabled", "persistence_failed", "imported", "import_rejected", "superseded"},
}


def validate_import_plan(plan: dict[str, Any]) -> None:
    """Reject source-independent contradictory Core states before opening Core."""
    declared_hash = str(plan.get("plan_sha256") or "")
    canonical_plan = dict(plan)
    canonical_plan.pop("plan_sha256", None)
    actual_hash = sha256(
        json.dumps(canonical_plan, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    if not declared_hash or declared_hash != actual_hash:
        raise CoreImportError("Import plan SHA-256 does not match its canonical contents")
    destination = plan.get("destination_rows", {})
    runs = destination.get("core_run", [])
    snapshots = destination.get("core_source_snapshot", [])
    if len(runs) != 1:
        raise CoreImportError("Core v1 importer validates exactly one run per plan")
    run = runs[0]
    kind = run.get("run_kind")
    if kind not in _RUN_EVIDENCE_BY_KIND:
        raise CoreImportError("Invalid Core run kind")
    if run.get("evidence_completeness_status") not in _RUN_EVIDENCE_BY_KIND[kind]:
        raise CoreImportError("Run evidence status contradicts run kind")
    if kind == "ledger_only" and snapshots:
        raise CoreImportError("Ledger-only run cannot carry a source snapshot")
    if kind == "snapshot_backed" and len(snapshots) != 1:
        raise CoreImportError("Snapshot-backed run requires exactly one source snapshot")
    if run.get("supersedes_run_id") == run.get("run_id"):
        raise CoreImportError("A Core run cannot supersede itself")
    for artifact in destination.get("core_artifact", []):
        pointer = bool(artifact.get("mutable_pointer_flag"))
        if pointer != (artifact.get("availability_status") == "mutable_pointer_only"):
            raise CoreImportError("Artifact pointer flag contradicts availability")
        hash_state = artifact.get("hash_validation_status")
        expected, observed = artifact.get("expected_sha256"), artifact.get("observed_sha256")
        if hash_state == "validated" and (pointer or not expected or not observed or expected != observed):
            raise CoreImportError("Validated artifact hash requires matching immutable hashes")
        if hash_state == "mismatch" and (pointer or not expected or not observed or expected == observed):
            raise CoreImportError("Mismatched artifact hash requires distinct immutable hashes")
    for finding in destination.get("core_quality_finding", []):
        if finding.get("selected_value") is not None and finding.get("resolution_status") not in {"resolved", "accepted_limitation"}:
            raise CoreImportError("Selected quality-finding value requires an explicit resolution state")


def _receipt_id(plan: dict[str, Any]) -> str:
    return sha256((str(plan["plan_sha256"]) + datetime.now(UTC).isoformat()).encode()).hexdigest()


def _one(cursor: Any, sql: str, params: tuple[Any, ...]) -> Any:
    cursor.execute(sql, params)
    return cursor.fetchone()


def execute_import_plan(
    *,
    target_database: str,
    plan: dict[str, Any],
    connection_factory: Callable[[str], Any] | None,
    production_authorization: Phase2CImportAuthorization | None = None,
) -> dict[str, Any]:
    """Execute a validated plan atomically in a Core-only target.

    Disposable validation needs no authorization record. A production target
    additionally requires a separate, exact-plan Phase 2C authorization
    record; the normal pipeline never supplies one. It performs no source
    read, no filesystem copy, and leaves source artifact paths as metadata.
    Existing matching run hashes are an idempotent no-op; a mismatched source
    hash is rejected before child writes.
    """
    if not plan.get("dry_run") or not plan.get("plan_sha256"):
        raise CoreImportError("Only deterministic dry-run import plans may cross the Core execution boundary")
    validate_import_plan(plan)
    production_target = str(target_database or "").casefold() == PRODUCTION_CORE_SCHEMA
    if production_target:
        if production_authorization is None:
            raise CoreImportError("Production Core import requires an explicit Phase 2C authorization record")
        production_authorization.validate_for(target_database=target_database, plan=plan)
    elif production_authorization is not None:
        raise CoreImportError("Phase 2C authorization cannot be used for a disposable Core target")
    target = validate_target_name(target_database, allow_production=production_target)
    if connection_factory is None:
        raise CoreMigrationError("An injected dedicated Core connection factory is required for import execution")
    run_rows = plan.get("destination_rows", {}).get("core_run", [])
    if len(run_rows) != 1:
        raise CoreImportError("Core v1 synthetic importer requires exactly one planned run")
    run = run_rows[0]
    receipt_id = _receipt_id(plan)
    connection = connection_factory(target)
    cursor = connection.cursor()
    try:
        cursor.execute("SET time_zone = '+00:00'")
        current = _one(cursor, "SELECT DATABASE()", ())
        if str(current[0] if current else "") != target:
            raise CoreMigrationError("Dedicated Core import connection did not select the approved target")
        existing = _one(cursor, "SELECT source_record_hash FROM core_run WHERE run_id = %s", (run["run_id"],))
        if existing:
            if str(existing[0] or "") != str(run["source_record_hash"]):
                raise CoreImportError("Existing Core run has a different source-record hash")
            connection.rollback()
            return {"status": "already_imported", "receipt_id": None, "run_id": run["run_id"]}
        profile = plan["destination_rows"]["core_profile"][0]
        cursor.execute(
            "INSERT INTO core_profile (profile_id, profile_hash, profile_name, profile_contract_json, created_at_utc, imported_at_utc) "
            "VALUES (%s, %s, %s, %s, UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))",
            (profile["profile_id"], profile["profile_hash"], profile["profile_name"], json.dumps(profile["profile_contract_json"]) if profile["profile_contract_json"] else None),
        )
        snapshot_id = None
        snapshots = plan["destination_rows"]["core_source_snapshot"]
        if snapshots:
            snapshot = snapshots[0]
            cursor.execute(
                "INSERT INTO core_source_snapshot (snapshot_key, source_catalogs_json, source_schema_name, source_database_role, source_schema_hash, source_query_contract_hash, source_query_contract_version, cohort_checksum, taxonomy_checksum, permission_snapshot_checksum, source_row_counts_json, source_record_hash, extracted_at_utc, snapshot_status, validation_status, import_receipt_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (snapshot["snapshot_key"], json.dumps(snapshot["source_catalogs_json"]), snapshot["source_schema_name"], snapshot["source_database_role"], snapshot["source_schema_hash"], snapshot["source_query_contract_hash"], snapshot["source_query_contract_version"], snapshot["cohort_checksum"], snapshot["taxonomy_checksum"], snapshot["permission_snapshot_checksum"], json.dumps(snapshot["source_row_counts_json"]), snapshot["source_record_hash"], snapshot["extracted_at_utc"], snapshot["snapshot_status"], snapshot["validation_status"], receipt_id),
            )
            snapshot_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO core_run (run_id, legacy_run_id, run_slot, profile_id, source_snapshot_id, run_kind, application_commit, application_version, configuration_hash, source_record_hash, run_started_at_utc, run_completed_at_utc, run_status, scope_kind, publication_applicability, evidence_completeness_status, import_receipt_id, artifact_count, metadata_json, imported_at_utc) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))",
            (run["run_id"], run["legacy_run_id"], run["run_slot"], run["profile_id"], snapshot_id, run["run_kind"], run["application_commit"], run["application_version"], run["configuration_hash"], run["source_record_hash"], run["run_started_at_utc"], run["run_completed_at_utc"], run["run_status"], run["scope_kind"], run["publication_applicability"], run["evidence_completeness_status"], receipt_id, run["artifact_count"], json.dumps(run["metadata_json"])),
        )
        for row in plan["destination_rows"]["core_run_sample"]:
            cursor.execute(
                "INSERT INTO core_run_sample (run_id,sample_key,sha256,source_sample_id,source_sample_namespace,observed_family,observed_type,inclusion_role,supervised_status,split_status,label_authority_state,evidence_state,record_checksum,source_record_hash) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                tuple(row[key] for key in ("run_id", "sample_key", "sha256", "source_sample_id", "source_sample_namespace", "observed_family", "observed_type", "inclusion_role", "supervised_status", "split_status", "label_authority_state", "evidence_state", "record_checksum", "source_record_hash")),
            )
        for row in plan["destination_rows"]["core_artifact"]:
            cursor.execute(
                "INSERT INTO core_artifact (run_id,artifact_role,source_snapshot_id,immutable_relative_path,legacy_source_path,sha256,expected_sha256,observed_sha256,byte_size,expected_byte_size,observed_byte_size,media_type,availability_status,hash_validation_status,mutable_pointer_flag,mutable_pointer_kind,retention_status,storage_root_class,archive_recovery_status,recoverability_confidence,evidence_status,import_receipt_id,imported_at_utc) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))",
                (row["run_id"], row["artifact_role"], snapshot_id, row["immutable_relative_path"], row["legacy_source_path"], row["sha256"], row["expected_sha256"], row["observed_sha256"], row["byte_size"], row["expected_byte_size"], row["observed_byte_size"], row["availability_status"], row["hash_validation_status"], row["mutable_pointer_flag"], row["mutable_pointer_kind"], row["retention_status"], row["storage_root_class"], row["archive_recovery_status"], row["recoverability_confidence"], row["evidence_status"], receipt_id),
            )
        for row in plan["destination_rows"]["core_quality_finding"]:
            cursor.execute(
                "INSERT INTO core_quality_finding (run_id,source_snapshot_id,sample_key,finding_code,finding_kind,severity,category,affected_dimension,message,finding_value,observed_values_json,selected_value,resolution_status,resolution_authority,evidence_path,source_record_hash,import_receipt_id,created_at_utc) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))",
                (row["run_id"], snapshot_id, row["sample_key"], row["finding_code"], row["finding_kind"], row["severity"], row["category"], row["affected_dimension"], row["message"], row["finding_value"], row["observed_values_json"], row["selected_value"], row["resolution_status"], row["resolution_authority"], row["evidence_path"], row["source_record_hash"], receipt_id),
            )
        connection.commit()
        return {"status": "imported", "receipt_id": receipt_id, "run_id": run["run_id"], "source_snapshot_id": snapshot_id}
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
