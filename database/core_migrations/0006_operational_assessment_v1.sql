-- Additive operational evidence revisions. Independent of experiment renames (0005).
-- Requires the Core migration ledger from 0002. Apply with explicit version selection.
CREATE TABLE core_assessment_artifact (
  artifact_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  PRIMARY KEY (artifact_sha256),
  CONSTRAINT chk_assessment_artifact_sha CHECK (artifact_sha256 REGEXP BINARY '^[0-9a-f]{64}$')
) ENGINE=InnoDB;

CREATE TABLE core_assessment_revision (
  assessment_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  artifact_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  revision BIGINT UNSIGNED NOT NULL,
  previous_assessment_id CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  input_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  assessed_at_utc VARCHAR(40) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  result_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  family_id BIGINT UNSIGNED GENERATED ALWAYS AS (CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(result_json,'$.assessment.family.value.id')),'null') AS UNSIGNED)) STORED,
  type_id BIGINT UNSIGNED GENERATED ALWAYS AS (CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(result_json,'$.assessment.type.value.id')),'null') AS UNSIGNED)) STORED,
  processing_status VARCHAR(40) GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(result_json,'$.processing.status'))) STORED,
  PRIMARY KEY (assessment_id),
  UNIQUE KEY uq_assessment_sha_revision (artifact_sha256,revision),
  UNIQUE KEY uq_assessment_sha_id (artifact_sha256,assessment_id),
  UNIQUE KEY uq_assessment_successor (previous_assessment_id),
  KEY ix_assessment_family (family_id),
  KEY ix_assessment_type (type_id),
  KEY ix_assessment_status (processing_status),
  CONSTRAINT fk_assessment_artifact FOREIGN KEY (artifact_sha256) REFERENCES core_assessment_artifact(artifact_sha256),
  CONSTRAINT fk_assessment_predecessor FOREIGN KEY (artifact_sha256,previous_assessment_id) REFERENCES core_assessment_revision(artifact_sha256,assessment_id),
  CONSTRAINT chk_assessment_id CHECK (assessment_id REGEXP BINARY '^[0-9a-f]{64}$'),
  CONSTRAINT chk_assessment_input CHECK (input_digest REGEXP BINARY '^[0-9a-f]{64}$'),
  CONSTRAINT chk_assessment_chain CHECK ((revision=1 AND previous_assessment_id IS NULL) OR (revision>1 AND previous_assessment_id IS NOT NULL)),
  CONSTRAINT chk_assessment_json CHECK (JSON_VALID(result_json)),
  CONSTRAINT chk_assessment_json_id CHECK (COALESCE(JSON_UNQUOTE(JSON_EXTRACT(result_json,'$.assessment_id'))=assessment_id,0)),
  CONSTRAINT chk_assessment_json_sha CHECK (COALESCE(JSON_UNQUOTE(JSON_EXTRACT(result_json,'$.artifact.sha256'))=artifact_sha256,0)),
  CONSTRAINT chk_assessment_json_revision CHECK (COALESCE(JSON_EXTRACT(result_json,'$.revision')=revision,0)),
  CONSTRAINT chk_assessment_json_previous CHECK (JSON_CONTAINS_PATH(result_json,'one','$.previous_assessment_id') AND (NULLIF(JSON_UNQUOTE(JSON_EXTRACT(result_json,'$.previous_assessment_id')),'null') <=> previous_assessment_id)),
  CONSTRAINT chk_assessment_json_time CHECK (COALESCE(JSON_UNQUOTE(JSON_EXTRACT(result_json,'$.assessed_at_utc'))=assessed_at_utc,0)),
  CONSTRAINT chk_assessment_contract CHECK (COALESCE(JSON_UNQUOTE(JSON_EXTRACT(result_json,'$.contract_version'))='obsidiandroid.artifact-assessment.v1',0)),
  CONSTRAINT chk_assessment_status CHECK (COALESCE(processing_status IN ('complete','complete_with_unresolved_fields','complete_with_conflict','insufficient_evidence','unsupported_artifact','error'),0))
) ENGINE=InnoDB;

CREATE SQL SECURITY INVOKER VIEW v_core_assessment_current AS
SELECT r.* FROM core_assessment_revision r
WHERE NOT EXISTS (SELECT 1 FROM core_assessment_revision newer
 WHERE newer.artifact_sha256=r.artifact_sha256 AND newer.revision>r.revision);

DELIMITER $$
CREATE TRIGGER core_assessment_no_update BEFORE UPDATE ON core_assessment_revision
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Assessment revisions are immutable'$$
CREATE TRIGGER core_assessment_no_delete BEFORE DELETE ON core_assessment_revision
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Assessment revisions are immutable'$$
CREATE TRIGGER core_assessment_append BEFORE INSERT ON core_assessment_revision
FOR EACH ROW
BEGIN
  DECLARE locked_sha CHAR(64);
  DECLARE last_revision BIGINT UNSIGNED DEFAULT 0;
  DECLARE last_id CHAR(64) DEFAULT NULL;
  SELECT artifact_sha256 INTO locked_sha FROM core_assessment_artifact
    WHERE artifact_sha256=NEW.artifact_sha256 FOR UPDATE;
  SELECT COALESCE(MAX(revision),0) INTO last_revision FROM core_assessment_revision
    WHERE artifact_sha256=NEW.artifact_sha256;
  IF last_revision>0 THEN
    SELECT assessment_id INTO last_id FROM core_assessment_revision
      WHERE artifact_sha256=NEW.artifact_sha256 AND revision=last_revision;
  END IF;
  IF NEW.revision <> last_revision+1 OR NOT (NEW.previous_assessment_id <=> last_id) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Revision must extend current assessment';
  END IF;
END$$
DELIMITER ;
