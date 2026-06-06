-- ObsidianDroid research database — core tables (DDL draft, V3.1.0)
-- Target schema: obsidiandroid_research (OBSIDIANDROID_RESEARCH_DB_NAME)
-- No runtime writes in V3.1.0; apply manually after review.

CREATE DATABASE IF NOT EXISTS obsidiandroid_research
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE obsidiandroid_research;

-- ---------------------------------------------------------------------------
-- profiles — canonical execution profiles and claim-surface metadata
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profiles (
  profile_id            VARCHAR(128)  NOT NULL,
  profile_role          VARCHAR(64)   NULL,
  claim_surface_code    VARCHAR(64)   NULL,
  training_label_field  VARCHAR(64)   NULL,
  support_floor_mode    VARCHAR(64)   NULL,
  run_slot              VARCHAR(64)   NULL,
  yaml_path             VARCHAR(512)  NULL,
  active_from_utc       DATETIME(6)   NULL,
  retired_at_utc        DATETIME(6)   NULL,
  created_at_utc        DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at_utc        DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (profile_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- runs — one row per governed run_id
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS runs (
  run_id                VARCHAR(64)   NOT NULL,
  profile_id            VARCHAR(128)  NOT NULL,
  run_slot              VARCHAR(64)   NULL,
  run_mode              VARCHAR(64)   NULL,
  run_started_at_utc    DATETIME(6)   NULL,
  run_finished_at_utc   DATETIME(6)   NULL,
  pipeline_status       VARCHAR(64)   NULL,
  claim_status          VARCHAR(64)   NULL,
  publication_ready     TINYINT(1)    NOT NULL DEFAULT 0,
  dataset_hash          CHAR(64)      NULL,
  split_hash            CHAR(64)      NULL,
  cohort_size           INT UNSIGNED  NULL,
  train_n               INT UNSIGNED  NULL,
  test_n                INT UNSIGNED  NULL,
  source_git_commit     CHAR(40)      NULL,
  source_git_tag        VARCHAR(128)  NULL,
  code_version          VARCHAR(64)   NULL,
  manifest_json         JSON          NULL,
  observability_json    JSON          NULL,
  artifact_root         VARCHAR(1024) NULL,
  created_at_utc        DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at_utc        DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (run_id),
  CONSTRAINT fk_runs_profile
    FOREIGN KEY (profile_id) REFERENCES profiles (profile_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- samples — lazy curated registry (not Erebus catalog replication)
-- Rows are inserted only when a sample_id appears in curated run artifacts.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS samples (
  sample_id             BIGINT        NOT NULL,
  sha256                CHAR(64)      NULL,
  package_name          VARCHAR(512)  NULL,
  first_seen_run_id     VARCHAR(64)   NULL,
  last_seen_run_id      VARCHAR(64)   NULL,
  erebus_row_hash       CHAR(64)      NULL,
  created_at_utc        DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at_utc        DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (sample_id),
  UNIQUE KEY uq_samples_sha256 (sha256),
  CONSTRAINT fk_samples_first_seen_run
    FOREIGN KEY (first_seen_run_id) REFERENCES runs (run_id),
  CONSTRAINT fk_samples_last_seen_run
    FOREIGN KEY (last_seen_run_id) REFERENCES runs (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- sample_label_facts — governed supervised labels per run
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sample_label_facts (
  run_id                      VARCHAR(64)   NOT NULL,
  sample_id                   BIGINT        NOT NULL,
  profile_id                  VARCHAR(128)  NOT NULL,
  family_id                   VARCHAR(128)  NULL,
  family_canonical            VARCHAR(256)  NULL,
  type_slug                   VARCHAR(128)  NULL,
  supervised_label            VARCHAR(256)  NULL,
  supervised_label_namespace  VARCHAR(128)  NULL,
  training_label_field        VARCHAR(64)   NULL,
  sample_label_kind           VARCHAR(64)   NULL,
  created_at_utc              DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (run_id, sample_id),
  CONSTRAINT fk_sample_label_facts_run
    FOREIGN KEY (run_id) REFERENCES runs (run_id),
  CONSTRAINT fk_sample_label_facts_sample
    FOREIGN KEY (sample_id) REFERENCES samples (sample_id),
  CONSTRAINT fk_sample_label_facts_profile
    FOREIGN KEY (profile_id) REFERENCES profiles (profile_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- profile_membership — cohort membership and curation state per sample
-- curation_state enum (V3.1): benchmark_include, exploratory_include,
-- diagnostic_only, audit_only, needs_review, exclude_from_training,
-- exclude_from_claims
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profile_membership (
  run_id                    VARCHAR(64)   NOT NULL,
  profile_id                VARCHAR(128)  NOT NULL,
  sample_id                 BIGINT        NOT NULL,
  membership_stage          VARCHAR(64)   NULL,
  curation_state            VARCHAR(64)   NOT NULL,
  benchmark_eligible        TINYINT(1)    NOT NULL DEFAULT 0,
  trainable_pool_included   TINYINT(1)    NOT NULL DEFAULT 0,
  exclusion_reason          VARCHAR(512)  NULL,
  created_at_utc            DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (run_id, sample_id),
  CONSTRAINT fk_profile_membership_run
    FOREIGN KEY (run_id) REFERENCES runs (run_id),
  CONSTRAINT fk_profile_membership_sample
    FOREIGN KEY (sample_id) REFERENCES samples (sample_id),
  CONSTRAINT fk_profile_membership_profile
    FOREIGN KEY (profile_id) REFERENCES profiles (profile_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- permission_vocabulary — run-scoped permission normalization
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS permission_vocabulary (
  run_id                  VARCHAR(64)   NOT NULL,
  vocabulary_version      VARCHAR(64)   NULL,
  entry_kind              VARCHAR(32)   NOT NULL,
  permission              VARCHAR(512)  NOT NULL,
  canonical_permission    VARCHAR(512)  NULL,
  alias_from              VARCHAR(512)  NULL,
  alias_to                VARCHAR(512)  NULL,
  source_scope            JSON          NULL,
  max_prevalence_pct      DECIMAL(8,4)  NULL,
  created_at_utc          DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (run_id, entry_kind, canonical_permission, permission),
  CONSTRAINT fk_permission_vocabulary_run
    FOREIGN KEY (run_id) REFERENCES runs (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- sample_permission_facts — long-form permission presence (sparse export)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sample_permission_facts (
  run_id                      VARCHAR(64)   NOT NULL,
  sample_id                   BIGINT        NOT NULL,
  permission_name             VARCHAR(512)  NOT NULL,
  canonical_permission        VARCHAR(512)  NULL,
  permission_present          TINYINT(1)    NOT NULL DEFAULT 0,
  permission_authority_bucket VARCHAR(64)   NULL,
  permission_risk_tier        VARCHAR(64)   NULL,
  permission_source           VARCHAR(64)   NULL,
  feature_column_name         VARCHAR(512)  NULL,
  created_at_utc              DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (run_id, sample_id, permission_name),
  CONSTRAINT fk_sample_permission_facts_run
    FOREIGN KEY (run_id) REFERENCES runs (run_id),
  CONSTRAINT fk_sample_permission_facts_sample
    FOREIGN KEY (sample_id) REFERENCES samples (sample_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- permission_pattern_facts — permission-pattern ladder rows
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS permission_pattern_facts (
  run_id              VARCHAR(64)   NOT NULL,
  fact_grain          VARCHAR(64)   NOT NULL,
  focus_key           VARCHAR(256)  NOT NULL,
  permission          VARCHAR(512)  NOT NULL,
  comparison_scope    VARCHAR(128)  NULL,
  pattern_score       DECIMAL(12,6) NULL,
  pattern_level       TINYINT       NULL,
  pattern_label       VARCHAR(128)  NULL,
  pattern_basis       VARCHAR(128)  NULL,
  pattern_confidence  VARCHAR(64)   NULL,
  pattern_reason      VARCHAR(512)  NULL,
  source_artifact     VARCHAR(512)  NULL,
  created_at_utc      DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (run_id, fact_grain, focus_key, permission, comparison_scope),
  CONSTRAINT fk_permission_pattern_facts_run
    FOREIGN KEY (run_id) REFERENCES runs (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- model_metrics — headline and ablation metrics per run
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_metrics (
  run_id                VARCHAR(64)   NOT NULL,
  model_name            VARCHAR(128)  NOT NULL,
  label_target          VARCHAR(128)  NOT NULL,
  experiment            VARCHAR(128)  NOT NULL DEFAULT '',
  feature_set           VARCHAR(128)  NULL,
  macro_f1              DECIMAL(10,6) NULL,
  weighted_f1           DECIMAL(10,6) NULL,
  accuracy              DECIMAL(10,6) NULL,
  primary_metric_name   VARCHAR(64)   NULL,
  primary_metric_value  DECIMAL(10,6) NULL,
  split_hash            CHAR(64)      NULL,
  train_n               INT UNSIGNED  NULL,
  test_n                INT UNSIGNED  NULL,
  created_at_utc        DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (run_id, model_name, label_target, experiment),
  CONSTRAINT fk_model_metrics_run
    FOREIGN KEY (run_id) REFERENCES runs (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- prediction_facts — per-sample prediction outcomes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prediction_facts (
  run_id                  VARCHAR(64)   NOT NULL,
  sample_id               BIGINT        NOT NULL,
  model_name              VARCHAR(128)  NOT NULL,
  true_label              VARCHAR(256)  NULL,
  predicted_label         VARCHAR(256)  NULL,
  confidence              DECIMAL(10,6) NULL,
  prediction_error        TINYINT(1)    NULL,
  shared_malware_type     TINYINT(1)    NULL,
  type_guard_suppressed   TINYINT(1)    NULL,
  created_at_utc          DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (run_id, sample_id, model_name),
  CONSTRAINT fk_prediction_facts_run
    FOREIGN KEY (run_id) REFERENCES runs (run_id),
  CONSTRAINT fk_prediction_facts_sample
    FOREIGN KEY (sample_id) REFERENCES samples (sample_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- quality_flags — run-, sample-, or family-level audit flags
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quality_flags (
  flag_id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  run_id            VARCHAR(64)     NOT NULL,
  sample_id         BIGINT          NULL,
  flag_scope        VARCHAR(32)     NOT NULL,
  flag_code         VARCHAR(128)    NOT NULL,
  severity          VARCHAR(32)     NULL,
  flag_value        VARCHAR(512)    NULL,
  rationale         TEXT            NULL,
  source_artifact   VARCHAR(512)    NULL,
  created_at_utc    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (flag_id),
  CONSTRAINT fk_quality_flags_run
    FOREIGN KEY (run_id) REFERENCES runs (run_id),
  CONSTRAINT fk_quality_flags_sample
    FOREIGN KEY (sample_id) REFERENCES samples (sample_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- split_assignments — frozen train/test/val membership
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS split_assignments (
  run_id              VARCHAR(64)   NOT NULL,
  sample_id           BIGINT        NOT NULL,
  split_role          VARCHAR(16)   NOT NULL,
  split_hash          CHAR(64)      NULL,
  label_field         VARCHAR(64)   NULL,
  label_target        VARCHAR(128)  NULL,
  active_class_count  INT UNSIGNED  NULL,
  overlap_flag        TINYINT(1)    NULL,
  created_at_utc      DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (run_id, sample_id),
  CONSTRAINT fk_split_assignments_run
    FOREIGN KEY (run_id) REFERENCES runs (run_id),
  CONSTRAINT fk_split_assignments_sample
    FOREIGN KEY (sample_id) REFERENCES samples (sample_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- release_manifests — official release packaging and git tag relationships
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS release_manifests (
  release_tag         VARCHAR(128)  NOT NULL,
  profile_id          VARCHAR(128)  NOT NULL,
  run_id              VARCHAR(64)   NOT NULL,
  git_commit          CHAR(40)      NULL,
  git_tag             VARCHAR(128)  NULL,
  code_version        VARCHAR(64)   NULL,
  importer_version    VARCHAR(64)   NULL,
  imported_at_utc     DATETIME(6)   NULL,
  manifest_json       JSON          NULL,
  created_at_utc      DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (release_tag, profile_id),
  CONSTRAINT fk_release_manifests_profile
    FOREIGN KEY (profile_id) REFERENCES profiles (profile_id),
  CONSTRAINT fk_release_manifests_run
    FOREIGN KEY (run_id) REFERENCES runs (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
