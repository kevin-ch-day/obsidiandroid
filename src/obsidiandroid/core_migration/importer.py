"""Synthetic/testable Core import executor; not connected to the normal pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable

from .authorization import (
    AuthorizationConsumptionLedger,
    Phase2CImportAuthorization,
    PRODUCTION_CORE_SCHEMA,
    mariadb_server_attestation,
    require_clean_repository_at_commit,
    validate_core_preflight_payload,
    validate_host_preflight_payload,
)
from .executor import CoreMigrationError, validate_target_name
from .mapping import CoreImportError, destination_reconciliation_contract


_RUN_EVIDENCE_BY_KIND = {
    "ledger_only": {"ledger_only", "incomplete", "persistence_disabled", "persistence_failed", "import_rejected", "superseded"},
    "snapshot_backed": {"snapshot_backed", "incomplete", "persistence_disabled", "persistence_failed", "imported", "import_rejected", "superseded"},
}

# These checkpoints exist solely to prove transactional rollback in a named
# disposable Phase 2C rehearsal schema.  They are intentionally not exposed by
# the production import CLI and are rejected before any production validation,
# authorization consumption, or database connection.
_DISPOSABLE_FAILURE_CHECKPOINTS = frozenset(
    {
        "after_profile_insert",
        "after_snapshot_insert",
        "after_run_insert",
        "after_samples_insert",
        "after_artifacts_insert",
        "after_quality_findings_insert",
    }
)


def _raise_if_rehearsal_failure(checkpoint: str | None, current: str) -> None:
    if checkpoint == current:
        raise CoreImportError(f"Controlled disposable rehearsal failure injected at {current}")


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
    if plan.get("destination_reconciliation") != destination_reconciliation_contract(destination):
        raise CoreImportError("Import plan destination reconciliation contract does not match its rows")
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


def _database_json(value: Any) -> str | None:
    """Serialize JSON once, preserving already-canonical JSON structures."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _database_datetime(value: Any) -> datetime | None:
    """Convert frozen ISO-8601 UTC evidence into MariaDB DATETIME input.

    Source extracts deliberately use an unambiguous trailing ``Z``. MariaDB's
    DATETIME parser accepts that form only with a truncation warning, which is
    a DataError under strict SQL mode. The Core schema stores UTC wall-clock
    DATETIME(6), so bind a timezone-normalized, naive ``datetime`` instead.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CoreImportError("Core import plan contains an invalid ISO-8601 timestamp") from exc
    else:
        raise CoreImportError("Core import plan contains an unsupported timestamp value")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _one(cursor: Any, sql: str, params: tuple[Any, ...]) -> Any:
    cursor.execute(sql, params)
    return cursor.fetchone()


def execute_import_plan(
    *,
    target_database: str,
    plan: dict[str, Any],
    connection_factory: Callable[[str], Any] | None,
    production_authorization: Phase2CImportAuthorization | None = None,
    authorization_consumption_ledger: AuthorizationConsumptionLedger | None = None,
    production_core_preflight: dict[str, Any] | None = None,
    production_host_preflight: dict[str, Any] | None = None,
    disposable_failure_checkpoint: str | None = None,
) -> dict[str, Any]:
    """Execute a validated plan atomically in a Core-only target.

    Disposable validation needs no authorization record. A production target
    additionally requires a separate, exact-plan Phase 2C authorization
    record; the normal pipeline never supplies one. It performs no source
    read, no filesystem copy, and leaves source artifact paths as metadata.
    Existing matching run hashes are an idempotent no-op; a mismatched source
    hash is rejected before child writes. ``disposable_failure_checkpoint`` is
    a test/rehearsal-only rollback probe and is never permitted for production.
    """
    if not plan.get("dry_run") or not plan.get("plan_sha256"):
        raise CoreImportError("Only deterministic dry-run import plans may cross the Core execution boundary")
    validate_import_plan(plan)
    production_target = str(target_database or "").casefold() == PRODUCTION_CORE_SCHEMA
    if disposable_failure_checkpoint is not None:
        if production_target:
            raise CoreImportError("Controlled failure injection is forbidden for production Core imports")
        if disposable_failure_checkpoint not in _DISPOSABLE_FAILURE_CHECKPOINTS:
            raise CoreImportError("Unknown controlled disposable rehearsal failure checkpoint")
    authorization_receipt_path: str | None = None
    if production_target:
        if production_authorization is None:
            raise CoreImportError("Production Core import requires an explicit Phase 2C authorization record")
        if authorization_consumption_ledger is None:
            raise CoreImportError("Production Core import requires a durable single-use authorization ledger")
        production_authorization.validate_for(target_database=target_database, plan=plan)
        validate_core_preflight_payload(production_core_preflight or {}, production_authorization)
        validate_host_preflight_payload(production_host_preflight or {}, production_authorization)
        repository_root = Path(__file__).resolve().parents[3]
        require_clean_repository_at_commit(repository_root, production_authorization.repository_commit)
        # Consume before opening the Core connection.  A failed or rejected
        # attempt needs a new authorization rather than silently reusing a
        # reviewed one-time record.
        authorization_receipt_path = authorization_consumption_ledger.consume(production_authorization)
    elif production_authorization is not None:
        raise CoreImportError("Phase 2C authorization cannot be used for a disposable Core target")
    elif authorization_consumption_ledger is not None:
        raise CoreImportError("A Phase 2C authorization ledger cannot be used for a disposable Core target")
    target = validate_target_name(target_database, allow_production=production_target)
    if disposable_failure_checkpoint is not None and not target.startswith("od_core_phase2c_rehearsal_"):
        raise CoreImportError("Controlled failure injection requires a named Phase 2C rehearsal schema")
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
        if production_target:
            cursor.execute("SELECT @@hostname, @@port, @@server_id, @@version, @@version_comment, CURRENT_USER()")
            server = cursor.fetchone()
            if not server or len(server) != 6:
                raise CoreImportError("Production Core server did not return a complete MariaDB attestation")
            server_identity = mariadb_server_attestation(
                hostname=server[0], port=server[1], server_id=server[2], version=server[3], version_comment=server[4]
            )
            writer_identity = str(server[5])
            if server_identity != production_authorization.target_server_identity:
                raise CoreImportError("Production Core server identity does not match the authorization")
            if writer_identity != production_authorization.writer_account:
                raise CoreImportError("Production Core writer account does not match the authorization")
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
            (profile["profile_id"], profile["profile_hash"], profile["profile_name"], _database_json(profile["profile_contract_json"])),
        )
        _raise_if_rehearsal_failure(disposable_failure_checkpoint, "after_profile_insert")
        snapshot_id = None
        snapshots = plan["destination_rows"]["core_source_snapshot"]
        if snapshots:
            snapshot = snapshots[0]
            cursor.execute(
                "INSERT INTO core_source_snapshot (snapshot_key, source_catalogs_json, source_schema_name, source_database_role, source_schema_hash, source_query_contract_hash, source_query_contract_version, cohort_checksum, taxonomy_checksum, permission_snapshot_checksum, source_row_counts_json, source_record_hash, extracted_at_utc, snapshot_status, validation_status, import_receipt_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (snapshot["snapshot_key"], _database_json(snapshot["source_catalogs_json"]), snapshot["source_schema_name"], snapshot["source_database_role"], snapshot["source_schema_hash"], snapshot["source_query_contract_hash"], snapshot["source_query_contract_version"], snapshot["cohort_checksum"], snapshot["taxonomy_checksum"], snapshot["permission_snapshot_checksum"], _database_json(snapshot["source_row_counts_json"]), snapshot["source_record_hash"], _database_datetime(snapshot["extracted_at_utc"]), snapshot["snapshot_status"], snapshot["validation_status"], receipt_id),
            )
            snapshot_id = cursor.lastrowid
        _raise_if_rehearsal_failure(disposable_failure_checkpoint, "after_snapshot_insert")
        cursor.execute(
            "INSERT INTO core_run (run_id, legacy_run_id, run_slot, profile_id, source_snapshot_id, run_kind, application_commit, application_version, configuration_hash, source_record_hash, run_started_at_utc, run_completed_at_utc, run_status, scope_kind, publication_applicability, evidence_completeness_status, import_receipt_id, artifact_count, metadata_json, imported_at_utc) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))",
            (run["run_id"], run["legacy_run_id"], run["run_slot"], run["profile_id"], snapshot_id, run["run_kind"], run["application_commit"], run["application_version"], run["configuration_hash"], run["source_record_hash"], _database_datetime(run["run_started_at_utc"]), _database_datetime(run["run_completed_at_utc"]), run["run_status"], run["scope_kind"], run["publication_applicability"], run["evidence_completeness_status"], receipt_id, run["artifact_count"], _database_json(run["metadata_json"])),
        )
        _raise_if_rehearsal_failure(disposable_failure_checkpoint, "after_run_insert")
        for row in plan["destination_rows"]["core_run_sample"]:
            cursor.execute(
                "INSERT INTO core_run_sample (run_id,sample_key,sha256,source_sample_id,source_sample_namespace,observed_family,observed_type,inclusion_role,supervised_status,split_status,label_authority_state,evidence_state,record_checksum,source_record_hash) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                tuple(row[key] for key in ("run_id", "sample_key", "sha256", "source_sample_id", "source_sample_namespace", "observed_family", "observed_type", "inclusion_role", "supervised_status", "split_status", "label_authority_state", "evidence_state", "record_checksum", "source_record_hash")),
            )
        _raise_if_rehearsal_failure(disposable_failure_checkpoint, "after_samples_insert")
        for row in plan["destination_rows"]["core_artifact"]:
            cursor.execute(
                "INSERT INTO core_artifact (run_id,artifact_role,source_snapshot_id,immutable_relative_path,legacy_source_path,sha256,expected_sha256,observed_sha256,byte_size,expected_byte_size,observed_byte_size,media_type,availability_status,hash_validation_status,mutable_pointer_flag,mutable_pointer_kind,retention_status,storage_root_class,archive_recovery_status,recoverability_confidence,evidence_status,import_receipt_id,imported_at_utc) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))",
                (row["run_id"], row["artifact_role"], snapshot_id, row["immutable_relative_path"], row["legacy_source_path"], row["sha256"], row["expected_sha256"], row["observed_sha256"], row["byte_size"], row["expected_byte_size"], row["observed_byte_size"], row["availability_status"], row["hash_validation_status"], row["mutable_pointer_flag"], row["mutable_pointer_kind"], row["retention_status"], row["storage_root_class"], row["archive_recovery_status"], row["recoverability_confidence"], row["evidence_status"], receipt_id),
            )
        _raise_if_rehearsal_failure(disposable_failure_checkpoint, "after_artifacts_insert")
        for row in plan["destination_rows"]["core_quality_finding"]:
            cursor.execute(
                "INSERT INTO core_quality_finding (run_id,source_snapshot_id,sample_key,finding_code,finding_kind,severity,category,affected_dimension,message,finding_value,observed_values_json,selected_value,resolution_status,resolution_authority,evidence_path,source_record_hash,import_receipt_id,created_at_utc) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))",
                (row["run_id"], snapshot_id, row["sample_key"], row["finding_code"], row["finding_kind"], row["severity"], row["category"], row["affected_dimension"], row["message"], row["finding_value"], _database_json(row["observed_values_json"]), row["selected_value"], row["resolution_status"], row["resolution_authority"], row["evidence_path"], row["source_record_hash"], receipt_id),
            )
        _raise_if_rehearsal_failure(disposable_failure_checkpoint, "after_quality_findings_insert")
        connection.commit()
        return {
            "status": "imported",
            "receipt_id": receipt_id,
            "authorization_consumption_receipt": authorization_receipt_path,
            "run_id": run["run_id"],
            "source_snapshot_id": snapshot_id,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
