-- Core v2 label and classification-output completion.
-- Additive only: labels and confusion counts belong to ObsidianDroid Core.

CREATE TABLE core_label_contract (
  label_contract_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  run_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  label_target VARCHAR(64) NOT NULL,
  taxonomy_version VARCHAR(128) NULL,
  label_universe_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  class_count INT UNSIGNED NOT NULL,
  authority_state VARCHAR(32) NOT NULL,
  source_snapshot_id BIGINT UNSIGNED NULL,
  created_at_utc DATETIME(6) NOT NULL,
  PRIMARY KEY (label_contract_id),
  UNIQUE KEY uq_core_label_contract_run_target (run_id, label_target),
  CONSTRAINT fk_core_label_contract_run FOREIGN KEY (run_id) REFERENCES core_run (run_id),
  CONSTRAINT fk_core_label_contract_snapshot FOREIGN KEY (source_snapshot_id) REFERENCES core_source_snapshot (source_snapshot_id),
  CONSTRAINT chk_core_label_contract_authority CHECK (authority_state IN ('governed','resolved','mixed','unknown'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_label_assignment (
  label_contract_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  sample_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  label_value VARCHAR(255) NOT NULL,
  label_role VARCHAR(32) NOT NULL,
  label_source VARCHAR(64) NOT NULL,
  authority_state VARCHAR(32) NOT NULL,
  PRIMARY KEY (label_contract_id, sample_key, label_role),
  CONSTRAINT fk_core_label_assignment_contract FOREIGN KEY (label_contract_id) REFERENCES core_label_contract (label_contract_id),
  CONSTRAINT chk_core_label_assignment_role CHECK (label_role IN ('target','observed','resolved','predicted')),
  CONSTRAINT chk_core_label_assignment_authority CHECK (authority_state IN ('governed','resolved','conflicted','unknown'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE core_confusion_cell (
  model_execution_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  label_contract_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  split_name VARCHAR(32) NOT NULL,
  true_label VARCHAR(255) NOT NULL,
  predicted_label VARCHAR(255) NOT NULL,
  sample_count INT UNSIGNED NOT NULL,
  PRIMARY KEY (model_execution_id, label_contract_id, split_name, true_label, predicted_label),
  CONSTRAINT fk_core_confusion_cell_execution FOREIGN KEY (model_execution_id) REFERENCES core_model_execution (model_execution_id),
  CONSTRAINT fk_core_confusion_cell_contract FOREIGN KEY (label_contract_id) REFERENCES core_label_contract (label_contract_id),
  CONSTRAINT chk_core_confusion_cell_split CHECK (split_name IN ('train','validation','test'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
