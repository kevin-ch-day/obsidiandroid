"""Deterministic source-to-Core mapping planner; it does not open databases or write Core."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Iterable


class CoreImportError(ValueError):
    """Raised for incomplete, conflicting, or non-deterministic import input."""


SOURCE_SURFACES = (
    "analysis_run",
    "analysis_snapshot",
    "analysis_snapshot_sample",
    "analysis_artifact",
    "snapshot_label_conflict",
)
SOURCE_QUERY_CONTRACT_VERSION = "core-approved-source-query-contract-v1"
_SHA256_LENGTH = 64
_PERSISTED_COLUMNS = {
    "core_profile": ("profile_id", "profile_hash", "profile_name", "profile_contract_json"),
    "core_source_snapshot": (
        "snapshot_key", "source_catalogs_json", "source_schema_name", "source_database_role",
        "source_schema_hash", "source_query_contract_hash", "source_query_contract_version",
        "cohort_checksum", "taxonomy_checksum", "permission_snapshot_checksum", "source_row_counts_json",
        "source_record_hash", "extracted_at_utc", "snapshot_status", "validation_status",
    ),
    "core_run": (
        "run_id", "legacy_run_id", "run_slot", "profile_id", "run_kind", "application_commit",
        "application_version", "configuration_hash", "source_record_hash", "run_started_at_utc",
        "run_completed_at_utc", "run_status", "scope_kind", "publication_applicability",
        "evidence_completeness_status", "artifact_count", "metadata_json",
    ),
    "core_run_sample": (
        "run_id", "sample_key", "sha256", "source_sample_id", "source_sample_namespace",
        "observed_family", "observed_type", "inclusion_role", "supervised_status", "split_status",
        "label_authority_state", "evidence_state", "record_checksum", "source_record_hash",
    ),
    "core_artifact": (
        "run_id", "artifact_role", "immutable_relative_path", "legacy_source_path", "sha256",
        "expected_sha256", "observed_sha256", "byte_size", "expected_byte_size", "observed_byte_size",
        "availability_status", "hash_validation_status", "mutable_pointer_flag", "mutable_pointer_kind",
        "retention_status", "storage_root_class", "archive_recovery_status", "recoverability_confidence",
        "evidence_status",
    ),
    "core_quality_finding": (
        "run_id", "sample_key", "finding_code", "finding_kind", "severity", "category",
        "affected_dimension", "message", "finding_value", "observed_values_json", "selected_value",
        "resolution_status", "resolution_authority", "evidence_path", "source_record_hash",
    ),
}
_RECONCILIATION_KEYS = {
    "core_profile": ("profile_id",),
    "core_source_snapshot": ("snapshot_key",),
    "core_run": ("run_id",),
    "core_run_sample": ("run_id", "sample_key"),
    "core_artifact": ("run_id", "artifact_role"),
    "core_quality_finding": ("run_id", "source_record_hash"),
}


def _canonical_hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _as_list(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(record) for record in records]


def _required(record: dict[str, Any], key: str, surface: str) -> Any:
    value = record.get(key)
    if value is None or str(value) == "":
        raise CoreImportError(f"{surface}.{key} is required for Core import planning")
    return value


def _validated_execution_contract(contract: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate Phase 2C bindings without manufacturing an execution authority."""
    if contract is None:
        return None
    normalized = dict(contract)
    value = str(normalized.get("source_extract_manifest_sha256") or "")
    if len(value) != _SHA256_LENGTH or any(character not in "0123456789abcdef" for character in value):
        raise CoreImportError("phase2c_execution_contract.source_extract_manifest_sha256 must be a lowercase SHA-256")
    repository_commit = str(normalized.get("repository_commit") or "")
    if len(repository_commit) not in {40, 64} or any(character not in "0123456789abcdef" for character in repository_commit):
        raise CoreImportError("phase2c_execution_contract.repository_commit must be a full Git object ID")
    checksums = normalized.get("migration_checksums")
    if not isinstance(checksums, dict) or set(checksums) != {"0001", "0002"}:
        raise CoreImportError("phase2c_execution_contract must bind 0001 and 0002 migration checksums")
    if any(
        len(str(value)) != _SHA256_LENGTH or any(character not in "0123456789abcdef" for character in str(value))
        for value in checksums.values()
    ):
        raise CoreImportError("phase2c_execution_contract migration checksums must be lowercase SHA-256 values")
    return {
        "source_extract_manifest_sha256": str(normalized["source_extract_manifest_sha256"]),
        "repository_commit": repository_commit,
        "migration_checksums": {version: str(checksums[version]) for version in sorted(checksums)},
    }


def destination_reconciliation_contract(destination: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """Describe exact persisted row content expected after a controlled import.

    Auto-generated IDs, timestamps, and receipt IDs are intentionally omitted.
    The resulting table contracts can be compared through the Core auditor
    without depending on source rows or a writer account.
    """
    contract: dict[str, dict[str, Any]] = {}
    for table, columns in _PERSISTED_COLUMNS.items():
        rows = destination.get(table, [])
        projected = [{column: row.get(column) for column in columns} for row in rows]
        key_columns = _RECONCILIATION_KEYS[table]
        ordered = sorted(projected, key=lambda row: tuple(str(row.get(key) or "") for key in key_columns))
        key_rows = [{key: row.get(key) for key in key_columns} for row in ordered]
        contract[table] = {
            "columns": list(columns),
            "key_columns": list(key_columns),
            "row_count": len(ordered),
            "key_sha256": _canonical_hash(key_rows),
            "row_sha256": _canonical_hash(ordered),
        }
    return contract


def build_import_plan(
    *,
    run: dict[str, Any],
    snapshots: Iterable[dict[str, Any]],
    samples: Iterable[dict[str, Any]],
    artifacts: Iterable[dict[str, Any]],
    conflicts: Iterable[dict[str, Any]],
    mapping_contract_version: str = "core-source-mapping-v1",
    phase2c_execution_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map source-shaped rows into ordered Core-shaped records without I/O.

    This intentionally preserves absence as ``None``/``unknown`` rather than
    inventing validation, snapshot, or artifact evidence.  It is a plan only;
    a separately reviewed Core writer may execute it later.
    """
    source_run = dict(run)
    execution_contract = _validated_execution_contract(phase2c_execution_contract)
    run_id = str(_required(source_run, "run_id", "analysis_run"))
    profile_id = str(_required(source_run, "profile_id", "analysis_run"))
    source_snapshots = _as_list(snapshots)
    source_samples = _as_list(samples)
    source_artifacts = _as_list(artifacts)
    source_conflicts = _as_list(conflicts)
    if len(source_snapshots) > 1:
        raise CoreImportError("Only one analysis_snapshot row per run is supported by Core v1 mapping")
    run_selection_rule = source_run.get("selection_rule_version")
    snapshot_selection_rule = source_snapshots[0].get("selection_rule_version") if source_snapshots else None
    if source_snapshots and run_selection_rule != snapshot_selection_rule:
        raise CoreImportError("analysis_run and analysis_snapshot selection_rule_version values disagree")
    for row in source_snapshots + source_samples + source_artifacts + source_conflicts:
        if str(_required(row, "run_id", "approved_source_surface")) != run_id:
            raise CoreImportError("Child source row run_id does not match analysis_run")
    sample_keys: set[str] = set()
    mapped_samples: list[dict[str, Any]] = []
    for row in sorted(source_samples, key=lambda item: (str(item.get("sha256") or ""), int(item.get("sample_id") or 0))):
        sample_key = str(row.get("sha256") or f"erebus_sample_id:{row.get('sample_id')}")
        if sample_key in sample_keys:
            raise CoreImportError(f"Duplicate deterministic Core sample_key {sample_key!r}")
        sample_keys.add(sample_key)
        mapped_samples.append(
            {
                "run_id": run_id,
                "sample_key": sample_key,
                "sha256": row.get("sha256"),
                "source_sample_id": row.get("sample_id"),
                "source_sample_namespace": "erebus_sample_id",
                "observed_family": row.get("family_canonical"),
                "observed_type": row.get("type_slug"),
                "inclusion_role": "aligned",
                "supervised_status": "unknown",
                "split_status": "not_assigned",
                "label_authority_state": "unknown",
                "evidence_state": "observed" if source_snapshots else "unknown",
                "record_checksum": row.get("feature_hash"),
                "source_record_hash": _canonical_hash(row),
            }
        )
    snapshot = source_snapshots[0] if source_snapshots else None
    snapshot_key = _canonical_hash(snapshot) if snapshot else None
    source_query_contract = {
        "contract_version": SOURCE_QUERY_CONTRACT_VERSION,
        "source_schema": "erebus_threat_intel_prod",
        "approved_surfaces": list(SOURCE_SURFACES),
        "selection_rule_version": snapshot_selection_rule,
    }
    mapped_artifacts = []
    for row in sorted(source_artifacts, key=lambda item: str(item.get("artifact_key") or "")):
        role = str(_required(row, "artifact_key", "analysis_artifact"))
        path = _required(row, "artifact_path", "analysis_artifact")
        mutable = ".latest." in str(path) or str(path).endswith(".latest")
        mapped_artifacts.append(
            {
                "run_id": run_id,
                "artifact_role": role,
                "immutable_relative_path": None,
                "legacy_source_path": path,
                "sha256": row.get("artifact_sha256"),
                "expected_sha256": row.get("artifact_sha256"),
                "observed_sha256": None,
                "byte_size": None,
                "expected_byte_size": None,
                "observed_byte_size": None,
                "availability_status": "mutable_pointer_only" if mutable else "legacy_path_unresolved",
                "hash_validation_status": "not_applicable" if mutable else "unavailable",
                "mutable_pointer_flag": bool(mutable),
                "mutable_pointer_kind": "latest_alias" if mutable else "none",
                "retention_status": "metadata_only",
                "storage_root_class": "legacy_external",
                "archive_recovery_status": "unknown",
                "recoverability_confidence": "unknown",
                "evidence_status": "metadata_only",
                "source_record_hash": _canonical_hash(row),
            }
        )
    mapped_findings = []
    for row in sorted(source_conflicts, key=lambda item: (str(item.get("sha256") or ""), str(item.get("conflict_type") or ""))):
        mapped_findings.append(
            {
                "run_id": run_id,
                "sample_key": row.get("sha256"),
                "finding_code": str(_required(row, "conflict_type", "snapshot_label_conflict")),
                "finding_kind": "source_conflict",
                "severity": "medium",
                "category": "snapshot_label",
                "affected_dimension": "label",
                "message": "Observed source snapshot label conflict retained without automatic resolution.",
                "finding_value": None,
                # The legacy surface stores text.  Preserve it as a JSON
                # string member rather than weakening Core's JSON contract.
                "observed_values_json": json.dumps({"source_observed_values": row.get("observed_values")}),
                "selected_value": None,
                "resolution_status": "open",
                "resolution_authority": None,
                "evidence_path": None,
                "source_record_hash": _canonical_hash(row),
            }
        )
    source_hash = _canonical_hash(
        {"run": source_run, "snapshots": source_snapshots, "samples": source_samples, "artifacts": source_artifacts, "conflicts": source_conflicts}
    )
    destination = {
        "core_profile": [{"profile_id": profile_id, "profile_name": profile_id, "profile_hash": None, "profile_contract_json": None}],
        "core_source_snapshot": [] if snapshot is None else [{
            "snapshot_key": snapshot_key,
            "source_catalogs_json": {
                "approved_surfaces": list(SOURCE_SURFACES),
                "vendor_constrained_run_flag": snapshot.get("vendor_constrained_run_flag"),
            },
            "source_schema_name": "erebus_threat_intel_prod",
            "source_database_role": "erebus_source",
            "source_schema_hash": None,
            "source_query_contract_hash": _canonical_hash(source_query_contract),
            "source_query_contract_version": SOURCE_QUERY_CONTRACT_VERSION,
            "cohort_checksum": snapshot.get("snapshot_sha256_hash"),
            "taxonomy_checksum": None,
            "permission_snapshot_checksum": None,
            "source_row_counts_json": {
                "analysis_snapshot_sample": int(snapshot["snapshot_row_count"]) if snapshot.get("snapshot_row_count") is not None else len(mapped_samples),
                "selected_vendor_count": snapshot.get("selected_vendor_count"),
                "included_vendor_count": snapshot.get("included_vendor_count"),
                "excluded_vendor_count": snapshot.get("excluded_vendor_count"),
            },
            "source_record_hash": _canonical_hash(snapshot),
            "extracted_at_utc": snapshot.get("extracted_at_utc"),
            "snapshot_status": "observed",
            "validation_status": "unknown",
        }],
        "core_run": [{
            "run_id": run_id,
            "legacy_run_id": run_id,
            "run_slot": None,
            "profile_id": profile_id,
            "run_kind": "snapshot_backed" if snapshot else "ledger_only",
            "application_commit": source_run.get("git_commit"),
            "application_version": None,
            "configuration_hash": source_run.get("snapshot_sha256_hash"),
            "source_record_hash": _canonical_hash(source_run),
            "run_started_at_utc": source_run.get("created_at_utc"),
            "run_completed_at_utc": None,
            "run_status": "completed",
            "scope_kind": "diagnostic",
            "publication_applicability": "not_applicable",
            "evidence_completeness_status": "imported" if snapshot else "ledger_only",
            "artifact_count": len(mapped_artifacts),
            "metadata_json": {
                "source_import": "planned_only",
                "mapping_contract_version": mapping_contract_version,
                "selection_rule_version": run_selection_rule,
                "vendor_constrained_run_flag": source_run.get("vendor_constrained_run_flag"),
                "selected_vendor_count": source_run.get("selected_vendor_count"),
                "included_vendor_count": source_run.get("included_vendor_count"),
                "excluded_vendor_count": source_run.get("excluded_vendor_count"),
                "source_notes": source_run.get("notes"),
            },
        }],
        "core_run_sample": mapped_samples,
        "core_artifact": mapped_artifacts,
        "core_quality_finding": mapped_findings,
    }
    plan = {
        "plan_version": "core-import-plan-v1",
        "mapping_contract_version": mapping_contract_version,
        "dry_run": True,
        "source_run_id": run_id,
        "source_record_hash": source_hash,
        "import_order": ["core_profile", "core_source_snapshot", "core_run", "core_run_sample", "core_artifact", "core_quality_finding"],
        "destination_rows": destination,
        "expected_counts": {table: len(rows) for table, rows in destination.items()},
        "destination_reconciliation": destination_reconciliation_contract(destination),
        "rejection_conditions": [
            "missing required source natural identity",
            "child run_id mismatch",
            "more than one source snapshot for run",
            "duplicate deterministic sample key",
            "source-record hash mismatch on re-execution",
        ],
        "rollback_scope": "Only active Core transaction rows; source rows and artifact files are never changed.",
    }
    if execution_contract is not None:
        plan["phase2c_execution_contract"] = execution_contract
    plan["plan_sha256"] = _canonical_hash(plan)
    return plan


def source_mapping_rows() -> tuple[dict[str, str], ...]:
    """Return explicit field mappings used by durable documentation and tests."""
    # The durable markdown matrix is authoritative for explanatory details.
    return (
        {"source": "analysis_run.run_id", "target": "core_run.run_id", "classification": "mapped_directly"},
        {"source": "analysis_snapshot.snapshot_sha256_hash", "target": "core_source_snapshot.cohort_checksum", "classification": "mapped_directly"},
        {"source": "analysis_snapshot_sample.feature_hash", "target": "core_run_sample.record_checksum", "classification": "mapped_directly"},
        {"source": "analysis_artifact.artifact_sha256", "target": "core_artifact.expected_sha256", "classification": "mapped_directly"},
        {"source": "snapshot_label_conflict.observed_values", "target": "core_quality_finding.observed_values_json", "classification": "retained_in_structured_metadata"},
    )
