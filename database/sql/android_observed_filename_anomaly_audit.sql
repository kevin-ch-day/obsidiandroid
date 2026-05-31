-- Read-only audit for suspicious `observed_filename` values in the Android
-- sample catalog.
--
-- Purpose:
--   - quantify obvious transport / formatting corruption
--   - surface the worst source-batch clusters
--   - give operators a bounded worklist before applying cleanup SQL
--
-- Run from the primary schema, for example:
--   mysql -t -D erebus_threat_intel_prod < database/sql/android_observed_filename_anomaly_audit.sql

SET NAMES utf8mb4;

-- -----------------------------------------------------------------------------
-- Q1) Top-level anomaly counts
-- -----------------------------------------------------------------------------
SELECT
    COUNT(*) AS android_rows,
    SUM(CASE WHEN observed_filename IS NULL OR TRIM(observed_filename) = '' THEN 1 ELSE 0 END) AS blank_rows,
    SUM(CASE WHEN observed_filename IS NOT NULL AND observed_filename <> TRIM(observed_filename) THEN 1 ELSE 0 END) AS leading_or_trailing_whitespace_rows,
    SUM(CASE WHEN observed_filename IS NOT NULL AND observed_filename REGEXP '[[:cntrl:]]' THEN 1 ELSE 0 END) AS control_char_rows,
    SUM(CASE WHEN observed_filename IS NOT NULL AND (
            observed_filename LIKE '%\\\\r%'
         OR observed_filename LIKE '%\\\\n%'
         OR observed_filename LIKE '%\\\\t%'
    ) THEN 1 ELSE 0 END) AS escaped_whitespace_literal_rows,
    SUM(CASE WHEN observed_filename IS NOT NULL AND observed_filename REGEXP '[^ -~]' THEN 1 ELSE 0 END) AS non_ascii_rows
FROM malware_sample_catalog
WHERE LOWER(TRIM(COALESCE(platform, ''))) = 'android';

-- -----------------------------------------------------------------------------
-- Q2) Batch / lane clusters for suspicious observed filenames
-- -----------------------------------------------------------------------------
SELECT
    COALESCE(NULLIF(TRIM(source_batch_label), ''), '<blank>') AS source_batch_label,
    COALESCE(NULLIF(TRIM(analysis_lane), ''), '<blank>') AS analysis_lane,
    COUNT(*) AS suspicious_rows,
    SUM(CASE WHEN observed_filename REGEXP '[[:cntrl:]]' THEN 1 ELSE 0 END) AS control_char_rows,
    SUM(CASE WHEN observed_filename LIKE '%\\\\r%' OR observed_filename LIKE '%\\\\n%' OR observed_filename LIKE '%\\\\t%' THEN 1 ELSE 0 END) AS escaped_whitespace_literal_rows,
    SUM(CASE WHEN observed_filename REGEXP '[^ -~]' THEN 1 ELSE 0 END) AS non_ascii_rows
FROM malware_sample_catalog
WHERE LOWER(TRIM(COALESCE(platform, ''))) = 'android'
  AND observed_filename IS NOT NULL
  AND (
         observed_filename <> TRIM(observed_filename)
      OR observed_filename REGEXP '[[:cntrl:]]'
      OR observed_filename LIKE '%\\\\r%'
      OR observed_filename LIKE '%\\\\n%'
      OR observed_filename LIKE '%\\\\t%'
      OR observed_filename REGEXP '[^ -~]'
  )
GROUP BY source_batch_label, analysis_lane
ORDER BY suspicious_rows DESC, source_batch_label, analysis_lane
LIMIT 100;

-- -----------------------------------------------------------------------------
-- Q3) Safe cleanup candidates: control-char / whitespace transport garbage only
-- -----------------------------------------------------------------------------
SELECT
    sample_id,
    sha256,
    COALESCE(NULLIF(TRIM(source_batch_label), ''), '<blank>') AS source_batch_label,
    COALESCE(NULLIF(TRIM(sample_label_kind), ''), '<blank>') AS sample_label_kind,
    observed_filename,
    HEX(observed_filename) AS observed_filename_hex
FROM malware_sample_catalog
WHERE LOWER(TRIM(COALESCE(platform, ''))) = 'android'
  AND observed_filename IS NOT NULL
  AND (
         observed_filename <> TRIM(observed_filename)
      OR observed_filename REGEXP '[[:cntrl:]]'
      OR observed_filename LIKE '%\\\\r%'
      OR observed_filename LIKE '%\\\\n%'
      OR observed_filename LIKE '%\\\\t%'
  )
ORDER BY sample_id
LIMIT 200;

-- -----------------------------------------------------------------------------
-- Q4) Review-only non-ASCII queue
-- -----------------------------------------------------------------------------
SELECT
    sample_id,
    sha256,
    COALESCE(NULLIF(TRIM(source_batch_label), ''), '<blank>') AS source_batch_label,
    observed_filename,
    HEX(observed_filename) AS observed_filename_hex
FROM malware_sample_catalog
WHERE LOWER(TRIM(COALESCE(platform, ''))) = 'android'
  AND observed_filename IS NOT NULL
  AND observed_filename REGEXP '[^ -~]'
ORDER BY sample_id
LIMIT 200;
