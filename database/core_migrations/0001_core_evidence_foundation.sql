-- ObsidianDroid Core Database v1 foundation.
-- DESIGN ONLY / PHASE 1: do not apply this file to a live database yet.
-- All timestamps are application-written UTC DATETIME(6) values.

CREATE TABLE core_schema_migration (
  migration_version VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  migration_name VARCHAR(128) NOT NULL,
  migration_checksum CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  applied_at_utc DATETIME(6) NOT NULL,
  application_commit CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  execution_status VARCHAR(32) NOT NULL,
  notes TEXT NULL,
  PRIMARY KEY (migration_version),
  UNIQUE KEY uq_core_schema_migration_checksum (migration_checksum)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_profile (
  profile_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  profile_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  profile_name VARCHAR(255) NULL,
  profile_contract_json JSON NULL,
  created_at_utc DATETIME(6) NOT NULL,
  PRIMARY KEY (profile_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_source_snapshot (
  source_snapshot_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_catalogs_json JSON NOT NULL,
  source_schema_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  source_query_contract_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  cohort_checksum CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  taxonomy_checksum CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  permission_snapshot_checksum CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  extracted_at_utc DATETIME(6) NULL,
  snapshot_status VARCHAR(32) NOT NULL,
  notes TEXT NULL,
  PRIMARY KEY (source_snapshot_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_run (
  run_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  legacy_run_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  run_slot VARCHAR(128) NULL,
  profile_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  source_snapshot_id BIGINT UNSIGNED NULL,
  application_commit CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  application_version VARCHAR(64) NULL,
  run_started_at_utc DATETIME(6) NULL,
  run_completed_at_utc DATETIME(6) NULL,
  run_status VARCHAR(32) NOT NULL,
  scope_kind VARCHAR(32) NOT NULL,
  publication_applicability VARCHAR(32) NOT NULL,
  evidence_completeness_status VARCHAR(32) NOT NULL,
  artifact_count INT UNSIGNED NOT NULL DEFAULT 0,
  imported_at_utc DATETIME(6) NOT NULL,
  PRIMARY KEY (run_id),
  KEY idx_core_run_profile (profile_id),
  KEY idx_core_run_snapshot (source_snapshot_id),
  CONSTRAINT fk_core_run_profile FOREIGN KEY (profile_id) REFERENCES core_profile (profile_id),
  CONSTRAINT fk_core_run_snapshot FOREIGN KEY (source_snapshot_id) REFERENCES core_source_snapshot (source_snapshot_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_run_sample (
  run_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  sample_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  source_sample_id BIGINT UNSIGNED NULL,
  observed_family VARCHAR(255) NULL,
  observed_type VARCHAR(128) NULL,
  inclusion_role VARCHAR(32) NOT NULL,
  supervised_status VARCHAR(32) NOT NULL,
  split_status VARCHAR(32) NOT NULL,
  record_checksum CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  PRIMARY KEY (run_id, sample_key),
  KEY idx_core_run_sample_sha256 (sha256),
  CONSTRAINT fk_core_run_sample_run FOREIGN KEY (run_id) REFERENCES core_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_artifact (
  run_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  artifact_role VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  immutable_relative_path TEXT NULL,
  legacy_source_path TEXT NULL,
  sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  byte_size BIGINT UNSIGNED NULL,
  media_type VARCHAR(128) NULL,
  availability_status VARCHAR(32) NOT NULL,
  hash_validation_status VARCHAR(32) NOT NULL,
  mutable_pointer_flag TINYINT(1) NOT NULL DEFAULT 0,
  retention_status VARCHAR(32) NOT NULL,
  created_at_utc DATETIME(6) NULL,
  imported_at_utc DATETIME(6) NOT NULL,
  PRIMARY KEY (run_id, artifact_role),
  CONSTRAINT fk_core_artifact_run FOREIGN KEY (run_id) REFERENCES core_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_quality_finding (
  finding_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  run_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  finding_code VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  severity VARCHAR(16) NOT NULL,
  category VARCHAR(64) NOT NULL,
  message TEXT NOT NULL,
  finding_value VARCHAR(255) NULL,
  evidence_path TEXT NULL,
  created_at_utc DATETIME(6) NOT NULL,
  PRIMARY KEY (finding_id),
  KEY idx_core_quality_finding_run (run_id),
  CONSTRAINT fk_core_quality_finding_run FOREIGN KEY (run_id) REFERENCES core_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
