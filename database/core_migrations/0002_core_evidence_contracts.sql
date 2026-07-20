-- ObsidianDroid Core v1 contract completion.
-- Apply only through the dedicated Core migration executor to an explicitly
-- approved Core target.  This migration preserves 0001 byte-for-byte.

ALTER TABLE core_schema_migration
  ADD COLUMN executor_id VARCHAR(128) NULL AFTER application_commit,
  ADD COLUMN mariadb_version VARCHAR(128) NULL AFTER executor_id,
  ADD COLUMN execution_duration_ms BIGINT UNSIGNED NULL AFTER mariadb_version,
  ADD COLUMN receipt_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER execution_duration_ms,
  -- A ledger record is written only after its DDL completes.  Failed work is
  -- represented by an external execution receipt, never by a misleading
  -- in-ledger "failed" version that could block a corrected migration.
  ADD CONSTRAINT chk_core_schema_migration_status
    CHECK (execution_status IN ('applied', 'rolled_back')),
  ADD UNIQUE KEY uq_core_schema_migration_receipt (receipt_id);

ALTER TABLE core_profile
  ADD COLUMN profile_version VARCHAR(64) NULL AFTER profile_name,
  ADD COLUMN contract_version VARCHAR(64) NULL AFTER profile_version,
  ADD COLUMN repository_commit CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER contract_version,
  ADD COLUMN source_provenance_json JSON NULL AFTER profile_contract_json,
  ADD COLUMN imported_at_utc DATETIME(6) NULL AFTER created_at_utc;

ALTER TABLE core_source_snapshot
  ADD COLUMN snapshot_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER source_snapshot_id,
  ADD COLUMN source_schema_name VARCHAR(128) NULL AFTER source_catalogs_json,
  ADD COLUMN source_database_role VARCHAR(32) NULL AFTER source_schema_name,
  ADD COLUMN source_query_contract_version VARCHAR(128) NULL AFTER source_query_contract_hash,
  ADD COLUMN source_row_counts_json JSON NULL AFTER source_query_contract_hash,
  ADD COLUMN source_record_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER permission_snapshot_checksum,
  ADD COLUMN validation_status VARCHAR(32) NOT NULL DEFAULT 'planned' AFTER snapshot_status,
  ADD COLUMN import_receipt_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER validation_status,
  ADD UNIQUE KEY uq_core_source_snapshot_key (snapshot_key),
  ADD CONSTRAINT chk_core_source_snapshot_status
    CHECK (snapshot_status IN ('planned', 'observed', 'validated', 'rejected')),
  ADD CONSTRAINT chk_core_source_snapshot_validation
    CHECK (validation_status IN ('planned', 'validated', 'rejected', 'unknown')),
  ADD CONSTRAINT chk_core_source_snapshot_role
    CHECK (source_database_role IS NULL OR source_database_role IN ('erebus_source', 'permission_intel_source', 'synthetic'));

ALTER TABLE core_run
  ADD COLUMN run_kind VARCHAR(32) NOT NULL DEFAULT 'ledger_only' AFTER legacy_run_id,
  ADD COLUMN configuration_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER application_version,
  ADD COLUMN source_record_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER configuration_hash,
  ADD COLUMN import_receipt_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER evidence_completeness_status,
  ADD COLUMN supersedes_run_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER import_receipt_id,
  ADD COLUMN metadata_json JSON NULL AFTER artifact_count,
  ADD CONSTRAINT fk_core_run_supersedes FOREIGN KEY (supersedes_run_id) REFERENCES core_run (run_id),
  ADD CONSTRAINT chk_core_run_kind CHECK (run_kind IN ('ledger_only', 'snapshot_backed')),
  ADD CONSTRAINT chk_core_run_status CHECK (run_status IN ('planned', 'running', 'completed', 'failed', 'rejected', 'superseded')),
  ADD CONSTRAINT chk_core_run_evidence CHECK (evidence_completeness_status IN ('ledger_only', 'snapshot_backed', 'incomplete', 'persistence_disabled', 'persistence_failed', 'imported', 'import_rejected', 'superseded'));

ALTER TABLE core_run
  ADD CONSTRAINT chk_core_run_snapshot_kind
    CHECK ((run_kind = 'ledger_only' AND source_snapshot_id IS NULL) OR (run_kind = 'snapshot_backed' AND source_snapshot_id IS NOT NULL)),
  ADD CONSTRAINT chk_core_run_not_self_superseded
    CHECK (supersedes_run_id IS NULL OR supersedes_run_id <> run_id),
  ADD CONSTRAINT chk_core_run_kind_evidence
    CHECK (
      (run_kind = 'ledger_only' AND evidence_completeness_status IN ('ledger_only', 'incomplete', 'persistence_disabled', 'persistence_failed', 'import_rejected', 'superseded'))
      OR
      (run_kind = 'snapshot_backed' AND evidence_completeness_status IN ('snapshot_backed', 'incomplete', 'persistence_disabled', 'persistence_failed', 'imported', 'import_rejected', 'superseded'))
    );

ALTER TABLE core_run_sample
  ADD COLUMN source_sample_namespace VARCHAR(64) NOT NULL DEFAULT 'erebus_sample_id' AFTER source_sample_id,
  ADD COLUMN label_authority_state VARCHAR(32) NOT NULL DEFAULT 'unknown' AFTER observed_type,
  ADD COLUMN evidence_state VARCHAR(32) NOT NULL DEFAULT 'unknown' AFTER label_authority_state,
  ADD COLUMN source_record_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER evidence_state,
  ADD CONSTRAINT chk_core_run_sample_inclusion CHECK (inclusion_role IN ('governed', 'prepared', 'aligned', 'trainable', 'train', 'test', 'excluded')),
  ADD CONSTRAINT chk_core_run_sample_supervised CHECK (supervised_status IN ('eligible', 'ineligible', 'not_applicable', 'unknown')),
  ADD CONSTRAINT chk_core_run_sample_split CHECK (split_status IN ('train', 'test', 'validation', 'not_assigned', 'excluded', 'unknown')),
  ADD CONSTRAINT chk_core_run_sample_authority CHECK (label_authority_state IN ('resolved', 'unresolved', 'conflicted', 'unknown'));

ALTER TABLE core_run_sample
  ADD CONSTRAINT chk_core_run_sample_evidence
    CHECK (evidence_state IN ('observed', 'snapshot_backed', 'imported', 'rejected', 'unknown'));

ALTER TABLE core_artifact
  ADD COLUMN source_snapshot_id BIGINT UNSIGNED NULL AFTER run_id,
  ADD COLUMN mutable_pointer_kind VARCHAR(32) NOT NULL DEFAULT 'none' AFTER mutable_pointer_flag,
  ADD COLUMN expected_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER sha256,
  ADD COLUMN observed_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER expected_sha256,
  ADD COLUMN expected_byte_size BIGINT UNSIGNED NULL AFTER byte_size,
  ADD COLUMN observed_byte_size BIGINT UNSIGNED NULL AFTER expected_byte_size,
  ADD COLUMN storage_root_class VARCHAR(32) NOT NULL DEFAULT 'unknown' AFTER media_type,
  ADD COLUMN archive_recovery_status VARCHAR(32) NOT NULL DEFAULT 'unknown' AFTER hash_validation_status,
  ADD COLUMN recoverability_confidence VARCHAR(16) NOT NULL DEFAULT 'unknown' AFTER archive_recovery_status,
  ADD COLUMN evidence_status VARCHAR(32) NOT NULL DEFAULT 'unknown' AFTER recoverability_confidence,
  ADD COLUMN import_receipt_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER retention_status,
  ADD CONSTRAINT fk_core_artifact_snapshot FOREIGN KEY (source_snapshot_id) REFERENCES core_source_snapshot (source_snapshot_id),
  ADD CONSTRAINT chk_core_artifact_availability CHECK (availability_status IN ('present', 'missing', 'mutable_pointer_only', 'legacy_path_unresolved', 'archive_candidate_found', 'unknown')),
  ADD CONSTRAINT chk_core_artifact_hash CHECK (hash_validation_status IN ('validated', 'mismatch', 'unavailable', 'not_recorded', 'not_applicable', 'unknown')),
  ADD CONSTRAINT chk_core_artifact_pointer CHECK (mutable_pointer_kind IN ('none', 'latest_alias', 'symlink', 'other'));

ALTER TABLE core_artifact
  ADD CONSTRAINT chk_core_artifact_pointer_pair
    CHECK ((mutable_pointer_flag = 0 AND mutable_pointer_kind = 'none') OR (mutable_pointer_flag = 1 AND mutable_pointer_kind <> 'none')),
  ADD CONSTRAINT chk_core_artifact_mutable_availability
    CHECK ((availability_status = 'mutable_pointer_only') = (mutable_pointer_flag = 1)),
  ADD CONSTRAINT chk_core_artifact_validated_hashes
    CHECK (hash_validation_status <> 'validated' OR (mutable_pointer_flag = 0 AND expected_sha256 IS NOT NULL AND observed_sha256 IS NOT NULL AND expected_sha256 = observed_sha256)),
  ADD CONSTRAINT chk_core_artifact_mismatch_hashes
    CHECK (hash_validation_status <> 'mismatch' OR (mutable_pointer_flag = 0 AND expected_sha256 IS NOT NULL AND observed_sha256 IS NOT NULL AND expected_sha256 <> observed_sha256)),
  ADD CONSTRAINT chk_core_artifact_retention
    CHECK (retention_status IN ('retained', 'metadata_only', 'archived', 'expired', 'synthetic', 'unknown')),
  ADD CONSTRAINT chk_core_artifact_storage_root
    CHECK (storage_root_class IN ('core_managed', 'legacy_external', 'archive', 'synthetic', 'unknown')),
  ADD CONSTRAINT chk_core_artifact_archive_recovery
    CHECK (archive_recovery_status IN ('recovered', 'candidate_found', 'not_found', 'not_applicable', 'unknown')),
  ADD CONSTRAINT chk_core_artifact_recoverability
    CHECK (recoverability_confidence IN ('high', 'medium', 'low', 'none', 'unknown')),
  ADD CONSTRAINT chk_core_artifact_evidence
    CHECK (evidence_status IN ('validated', 'metadata_only', 'mutable_pointer_only', 'hash_mismatch', 'present_unvalidated', 'synthetic', 'unknown'));

ALTER TABLE core_quality_finding
  ADD COLUMN source_snapshot_id BIGINT UNSIGNED NULL AFTER run_id,
  ADD COLUMN sample_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER source_snapshot_id,
  ADD COLUMN finding_kind VARCHAR(64) NOT NULL DEFAULT 'source_conflict' AFTER finding_code,
  ADD COLUMN affected_dimension VARCHAR(64) NULL AFTER category,
  ADD COLUMN observed_values_json JSON NULL AFTER finding_value,
  ADD COLUMN selected_value VARCHAR(255) NULL AFTER observed_values_json,
  ADD COLUMN resolution_status VARCHAR(32) NOT NULL DEFAULT 'open' AFTER selected_value,
  ADD COLUMN resolution_authority VARCHAR(128) NULL AFTER resolution_status,
  ADD COLUMN reviewed_at_utc DATETIME(6) NULL AFTER created_at_utc,
  ADD COLUMN source_record_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER reviewed_at_utc,
  ADD COLUMN import_receipt_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER reviewed_at_utc,
  ADD CONSTRAINT fk_core_quality_finding_snapshot FOREIGN KEY (source_snapshot_id) REFERENCES core_source_snapshot (source_snapshot_id),
  ADD CONSTRAINT chk_core_quality_finding_state CHECK (resolution_status IN ('open', 'reviewed', 'resolved', 'accepted_limitation', 'rejected', 'superseded')),
  ADD CONSTRAINT chk_core_quality_finding_selected CHECK (selected_value IS NULL OR resolution_status IN ('resolved', 'accepted_limitation'));

ALTER TABLE core_quality_finding
  ADD UNIQUE KEY uq_core_quality_finding_source_record (run_id, source_record_hash);
