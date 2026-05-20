-- Template load path for parser-enriched vendor evidence CSV.
--
-- Intended input:
--   output/diagnostics/label_authority_vendor_evidence_seed_latest.csv
--
-- This script is deliberately a template:
--   - adjust the CSV path for the target environment
--   - review the staging rows before inserting into malware_family_label_evidence
--   - do not run on production first

SET NAMES utf8mb4;

DROP TEMPORARY TABLE IF EXISTS tmp_label_authority_vendor_evidence_load;
CREATE TEMPORARY TABLE tmp_label_authority_vendor_evidence_load (
    sample_id INT UNSIGNED NOT NULL,
    vendor_key VARCHAR(128) NOT NULL,
    raw_vendor_label VARCHAR(512) NOT NULL,
    parsed_family_token VARCHAR(255) NULL,
    parsed_type_token VARCHAR(128) NULL,
    parsed_class_token VARCHAR(128) NULL,
    generic_token_flag TINYINT(1) NOT NULL,
    parser_name VARCHAR(128) NOT NULL,
    parser_version VARCHAR(64) NULL,
    parser_confidence_score DECIMAL(5,4) NULL,
    source_report_date_utc DATETIME NULL,
    is_active TINYINT(1) NOT NULL,
    notes TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Example for local/staging MySQL with LOCAL INFILE enabled:
-- LOAD DATA LOCAL INFILE '/absolute/path/to/output/diagnostics/label_authority_vendor_evidence_seed_latest.csv'
-- INTO TABLE tmp_label_authority_vendor_evidence_load
-- FIELDS TERMINATED BY ','
-- OPTIONALLY ENCLOSED BY '"'
-- LINES TERMINATED BY '\n'
-- IGNORE 1 LINES
-- (
--     sample_id,
--     vendor_key,
--     raw_vendor_label,
--     parsed_family_token,
--     parsed_type_token,
--     parsed_class_token,
--     generic_token_flag,
--     parser_name,
--     parser_version,
--     parser_confidence_score,
--     source_report_date_utc,
--     is_active,
--     notes
-- );

-- Review staging contents before insert.
SELECT COUNT(*) AS staged_rows FROM tmp_label_authority_vendor_evidence_load;

SELECT
    vendor_key,
    COUNT(*) AS staged_rows,
    ROUND(AVG(generic_token_flag) * 100, 2) AS generic_pct
FROM tmp_label_authority_vendor_evidence_load
GROUP BY vendor_key
ORDER BY staged_rows DESC, vendor_key ASC;

-- Insert only new active evidence rows.
INSERT INTO malware_family_label_evidence (
    sample_id,
    vendor_key,
    raw_vendor_label,
    parsed_family_token,
    parsed_type_token,
    parsed_class_token,
    generic_token_flag,
    parser_name,
    parser_version,
    parser_confidence_score,
    source_report_date_utc,
    is_active,
    notes
)
SELECT
    s.sample_id,
    LOWER(TRIM(s.vendor_key)) AS vendor_key,
    s.raw_vendor_label,
    NULLIF(LOWER(TRIM(s.parsed_family_token)), '') AS parsed_family_token,
    NULLIF(LOWER(TRIM(s.parsed_type_token)), '') AS parsed_type_token,
    NULLIF(LOWER(TRIM(s.parsed_class_token)), '') AS parsed_class_token,
    s.generic_token_flag,
    s.parser_name,
    s.parser_version,
    s.parser_confidence_score,
    s.source_report_date_utc,
    s.is_active,
    s.notes
FROM tmp_label_authority_vendor_evidence_load AS s
LEFT JOIN malware_family_label_evidence AS e
    ON e.sample_id = s.sample_id
   AND e.vendor_key = LOWER(TRIM(s.vendor_key))
   AND e.raw_vendor_label = s.raw_vendor_label
   AND e.parser_name = s.parser_name
   AND e.is_active = 1
WHERE e.evidence_id IS NULL;

-- Post-load sanity snapshot.
SELECT
    vendor_key,
    COUNT(*) AS loaded_rows
FROM malware_family_label_evidence
WHERE parser_name LIKE 'vendor_parser::%'
  AND is_active = 1
GROUP BY vendor_key
ORDER BY loaded_rows DESC, vendor_key ASC;
