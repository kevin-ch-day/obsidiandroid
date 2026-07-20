-- ObsidianDroid Core v2 generated-results foundation.
-- Apply only through the dedicated Core migration executor.  This additive
-- migration creates Core-owned result records and never reads source schemas.

CREATE TABLE core_run_stage (
  run_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  stage_name VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  stage_status VARCHAR(32) NOT NULL,
  started_at_utc DATETIME(6) NULL,
  completed_at_utc DATETIME(6) NULL,
  duration_ms BIGINT UNSIGNED NULL,
  failure_class VARCHAR(128) NULL,
  details_json JSON NULL,
  PRIMARY KEY (run_id, stage_name),
  CONSTRAINT fk_core_run_stage_run FOREIGN KEY (run_id) REFERENCES core_run (run_id),
  CONSTRAINT chk_core_run_stage_status CHECK (stage_status IN ('planned','running','completed','skipped','failed','interrupted'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_feature_contract (
  feature_contract_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  run_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  contract_name VARCHAR(128) NOT NULL,
  modality VARCHAR(64) NOT NULL,
  ordered_column_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  column_count INT UNSIGNED NOT NULL,
  leakage_assessment VARCHAR(32) NOT NULL,
  contract_json JSON NOT NULL,
  artifact_role VARCHAR(128) NULL,
  created_at_utc DATETIME(6) NOT NULL,
  PRIMARY KEY (feature_contract_id),
  UNIQUE KEY uq_core_feature_contract_run_name (run_id, contract_name),
  CONSTRAINT fk_core_feature_contract_run FOREIGN KEY (run_id) REFERENCES core_run (run_id),
  CONSTRAINT chk_core_feature_contract_leakage CHECK (leakage_assessment IN ('safe','label_informed','unknown','not_assessed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_split_ledger (
  run_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  split_contract_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  sample_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  split_name VARCHAR(32) NOT NULL,
  label_value VARCHAR(255) NULL,
  lineage_component_id VARCHAR(128) NULL,
  PRIMARY KEY (run_id, split_contract_hash, sample_key),
  CONSTRAINT fk_core_split_ledger_run FOREIGN KEY (run_id) REFERENCES core_run (run_id),
  CONSTRAINT chk_core_split_ledger_split CHECK (split_name IN ('train','validation','test','excluded'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_model_execution (
  model_execution_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  run_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  model_name VARCHAR(64) NOT NULL,
  evaluation_scope VARCHAR(64) NOT NULL,
  feature_contract_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  split_contract_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  estimator_config_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  model_artifact_role VARCHAR(128) NULL,
  promoted_flag TINYINT(1) NOT NULL DEFAULT 0,
  execution_status VARCHAR(32) NOT NULL,
  created_at_utc DATETIME(6) NOT NULL,
  PRIMARY KEY (model_execution_id),
  UNIQUE KEY uq_core_model_execution_scope (run_id, model_name, evaluation_scope, feature_contract_id, split_contract_hash),
  CONSTRAINT fk_core_model_execution_run FOREIGN KEY (run_id) REFERENCES core_run (run_id),
  CONSTRAINT fk_core_model_execution_feature FOREIGN KEY (feature_contract_id) REFERENCES core_feature_contract (feature_contract_id),
  CONSTRAINT chk_core_model_execution_status CHECK (execution_status IN ('planned','completed','failed','skipped'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_model_metric (
  model_execution_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  metric_name VARCHAR(64) NOT NULL,
  metric_value DOUBLE NULL,
  metric_universe_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  metric_details_json JSON NULL,
  PRIMARY KEY (model_execution_id, metric_name),
  CONSTRAINT fk_core_model_metric_execution FOREIGN KEY (model_execution_id) REFERENCES core_model_execution (model_execution_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_prediction (
  model_execution_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  sample_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  split_name VARCHAR(32) NOT NULL,
  true_label VARCHAR(255) NULL,
  predicted_label VARCHAR(255) NULL,
  confidence DOUBLE NULL,
  prediction_rank SMALLINT UNSIGNED NOT NULL DEFAULT 1,
  PRIMARY KEY (model_execution_id, sample_key, prediction_rank),
  CONSTRAINT fk_core_prediction_execution FOREIGN KEY (model_execution_id) REFERENCES core_model_execution (model_execution_id),
  CONSTRAINT chk_core_prediction_split CHECK (split_name IN ('train','validation','test'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_experiment (
  experiment_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  run_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  experiment_kind VARCHAR(32) NOT NULL,
  experiment_name VARCHAR(128) NOT NULL,
  feature_contract_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  experiment_config_json JSON NOT NULL,
  execution_status VARCHAR(32) NOT NULL,
  PRIMARY KEY (experiment_id),
  UNIQUE KEY uq_core_experiment_run_name (run_id, experiment_kind, experiment_name),
  CONSTRAINT fk_core_experiment_run FOREIGN KEY (run_id) REFERENCES core_run (run_id),
  CONSTRAINT fk_core_experiment_feature FOREIGN KEY (feature_contract_id) REFERENCES core_feature_contract (feature_contract_id),
  CONSTRAINT chk_core_experiment_kind CHECK (experiment_kind IN ('ablation','sensitivity','benchmark')),
  CONSTRAINT chk_core_experiment_status CHECK (execution_status IN ('planned','completed','failed','skipped'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_experiment_metric (
  experiment_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  model_name VARCHAR(64) NOT NULL,
  metric_name VARCHAR(64) NOT NULL,
  metric_value DOUBLE NULL,
  metric_details_json JSON NULL,
  PRIMARY KEY (experiment_id, model_name, metric_name),
  CONSTRAINT fk_core_experiment_metric_experiment FOREIGN KEY (experiment_id) REFERENCES core_experiment (experiment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_permission_measure (
  run_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  measure_kind VARCHAR(64) NOT NULL,
  view_mode VARCHAR(32) NOT NULL DEFAULT 'default',
  group_type VARCHAR(32) NOT NULL DEFAULT 'cohort',
  group_key VARCHAR(255) NOT NULL DEFAULT '',
  permission_string VARCHAR(255) NOT NULL DEFAULT '',
  observation_year SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  metric_name VARCHAR(64) NOT NULL,
  metric_value DOUBLE NULL,
  support_count INT UNSIGNED NULL,
  dimensions_json JSON NULL,
  PRIMARY KEY (run_id, measure_kind, view_mode, group_type, group_key, permission_string, observation_year, metric_name),
  CONSTRAINT fk_core_permission_measure_run FOREIGN KEY (run_id) REFERENCES core_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
