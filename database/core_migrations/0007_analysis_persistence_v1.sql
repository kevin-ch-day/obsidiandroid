-- Reuses the normalized results tables finalized by 0005. No assessment changes.
ALTER TABLE core_run
 ADD COLUMN analysis_contract_version VARCHAR(32) NULL,
 ADD COLUMN analysis_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 ADD COLUMN replay_of_run_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 ADD KEY idx_analysis_fingerprint (analysis_fingerprint),
 ADD CONSTRAINT fk_analysis_replay FOREIGN KEY (replay_of_run_id) REFERENCES core_run(run_id),
 DROP CONSTRAINT chk_core_run_status,
 ADD CONSTRAINT chk_core_run_status CHECK (run_status IN ('planned','running','completed','failed','cancelled','rejected','superseded'));
ALTER TABLE model_execution ADD COLUMN execution_metadata_json JSON NULL;
ALTER TABLE prediction
 ADD COLUMN prediction_status VARCHAR(32) NOT NULL DEFAULT 'PREDICTED',
 ADD COLUMN prediction_details_json JSON NULL,
 DROP CONSTRAINT chk_core_prediction_split,
 ADD CONSTRAINT chk_core_prediction_split CHECK (split_name IN ('train','validation','test','inference_only','excluded')),
 ADD CONSTRAINT chk_prediction_status CHECK (prediction_status IN ('PREDICTED','EXCLUDED','FEATURE_INCOMPLETE','LABEL_UNAVAILABLE','MODEL_ERROR','INVALID_ARTIFACT','NOT_APPLICABLE'));
ALTER TABLE split_ledger
 ADD COLUMN fold_number INT UNSIGNED NOT NULL DEFAULT 0,
 DROP CONSTRAINT chk_core_split_ledger_split,
 ADD CONSTRAINT chk_core_split_ledger_split CHECK (split_name IN ('train','validation','test','inference_only','excluded'));
ALTER TABLE core_artifact ADD COLUMN required_flag TINYINT(1) NOT NULL DEFAULT 1;
DELIMITER $$
CREATE TRIGGER analysis_run_immutable BEFORE UPDATE ON core_run FOR EACH ROW
BEGIN
 IF OLD.analysis_contract_version IS NOT NULL AND OLD.run_status IN ('completed','failed','cancelled') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Terminal analytical run is immutable';
 END IF;
 IF OLD.analysis_contract_version IS NOT NULL AND (NEW.run_id<>OLD.run_id OR NEW.profile_id<>OLD.profile_id OR NOT(NEW.analysis_contract_version<=>OLD.analysis_contract_version)) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical run identity is immutable';
 END IF;
END$$
CREATE TRIGGER analysis_run_no_delete BEFORE DELETE ON core_run FOR EACH ROW
BEGIN
 IF OLD.analysis_contract_version IS NOT NULL THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical runs cannot be deleted';
 END IF;
END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER ap_core_run_sample_insert BEFORE INSERT ON core_run_sample FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=NEW.run_id AND r.analysis_contract_version IS NOT NULL AND r.run_status <> 'running') THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_core_run_sample_update BEFORE UPDATE ON core_run_sample FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=OLD.run_id AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_core_run_sample_delete BEFORE DELETE ON core_run_sample FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=OLD.run_id AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_core_artifact_insert BEFORE INSERT ON core_artifact FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=NEW.run_id AND r.analysis_contract_version IS NOT NULL AND r.run_status <> 'running') THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_core_artifact_update BEFORE UPDATE ON core_artifact FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=OLD.run_id AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_core_artifact_delete BEFORE DELETE ON core_artifact FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=OLD.run_id AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_run_stage_insert BEFORE INSERT ON run_stage FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=NEW.run_id AND r.analysis_contract_version IS NOT NULL AND r.run_status <> 'running') THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_run_stage_update BEFORE UPDATE ON run_stage FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=OLD.run_id AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_run_stage_delete BEFORE DELETE ON run_stage FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=OLD.run_id AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_feature_contract_insert BEFORE INSERT ON feature_contract FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=NEW.run_id AND r.analysis_contract_version IS NOT NULL AND r.run_status <> 'running') THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_feature_contract_update BEFORE UPDATE ON feature_contract FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=OLD.run_id AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_feature_contract_delete BEFORE DELETE ON feature_contract FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=OLD.run_id AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_split_ledger_insert BEFORE INSERT ON split_ledger FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=NEW.run_id AND r.analysis_contract_version IS NOT NULL AND r.run_status <> 'running') THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_split_ledger_update BEFORE UPDATE ON split_ledger FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=OLD.run_id AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_split_ledger_delete BEFORE DELETE ON split_ledger FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=OLD.run_id AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_model_execution_insert BEFORE INSERT ON model_execution FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=NEW.run_id AND r.analysis_contract_version IS NOT NULL AND r.run_status <> 'running') THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_model_execution_update BEFORE UPDATE ON model_execution FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=OLD.run_id AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_model_execution_delete BEFORE DELETE ON model_execution FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=OLD.run_id AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_label_contract_insert BEFORE INSERT ON label_contract FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=NEW.run_id AND r.analysis_contract_version IS NOT NULL AND r.run_status <> 'running') THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_label_contract_update BEFORE UPDATE ON label_contract FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=OLD.run_id AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_label_contract_delete BEFORE DELETE ON label_contract FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=OLD.run_id AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_model_metric_insert BEFORE INSERT ON model_metric FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=(SELECT run_id FROM model_execution WHERE model_execution_id=NEW.model_execution_id) AND r.analysis_contract_version IS NOT NULL AND r.run_status <> 'running') THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_model_metric_update BEFORE UPDATE ON model_metric FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=(SELECT run_id FROM model_execution WHERE model_execution_id=OLD.model_execution_id) AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_model_metric_delete BEFORE DELETE ON model_metric FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=(SELECT run_id FROM model_execution WHERE model_execution_id=OLD.model_execution_id) AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_prediction_insert BEFORE INSERT ON prediction FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=(SELECT run_id FROM model_execution WHERE model_execution_id=NEW.model_execution_id) AND r.analysis_contract_version IS NOT NULL AND r.run_status <> 'running') THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_prediction_update BEFORE UPDATE ON prediction FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=(SELECT run_id FROM model_execution WHERE model_execution_id=OLD.model_execution_id) AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_prediction_delete BEFORE DELETE ON prediction FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=(SELECT run_id FROM model_execution WHERE model_execution_id=OLD.model_execution_id) AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_confusion_cell_insert BEFORE INSERT ON confusion_cell FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=(SELECT run_id FROM model_execution WHERE model_execution_id=NEW.model_execution_id) AND r.analysis_contract_version IS NOT NULL AND r.run_status <> 'running') THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_confusion_cell_update BEFORE UPDATE ON confusion_cell FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=(SELECT run_id FROM model_execution WHERE model_execution_id=OLD.model_execution_id) AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
CREATE TRIGGER ap_confusion_cell_delete BEFORE DELETE ON confusion_cell FOR EACH ROW
BEGIN
 IF EXISTS(SELECT 1 FROM core_run r WHERE r.run_id=(SELECT run_id FROM model_execution WHERE model_execution_id=OLD.model_execution_id) AND r.analysis_contract_version IS NOT NULL AND TRUE) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Analytical child mutation blocked';
 END IF;
END$$
DELIMITER ;
