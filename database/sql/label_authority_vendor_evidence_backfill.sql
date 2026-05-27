-- Label authority vendor-evidence backfill helpers.
--
-- Use this only after `label_authority_foundation.sql` has been applied.
-- This script seeds `malware_family_label_evidence` from the current wide
-- `virustotal_sample_vendor_engine_verdicts` table without changing any
-- governed family/type assignments.
--
-- First-pass scope:
--   1. unpivot the core parser-set vendor columns into a long evidence shape
--   2. preserve raw vendor label text and report timestamp
--   3. leave parsed family/type/class tokens NULL for later parser-enriched ETL
--
-- Notes:
--   - This is deliberately conservative: it imports non-empty positive-detection
--     labels only and leaves authority untouched.
--   - It is idempotent at the evidence-identity level, including parser version
--     and source report timestamp, so reruns do not duplicate identical rows.

SET NAMES utf8mb4;

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
WITH vendor_long AS (
    SELECT sample_id, updated_at AS source_report_date_utc, 'ahnlab_v3' AS vendor_key, ahnlab_v3 AS raw_vendor_label
    FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, updated_at, 'alibaba', alibaba FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, updated_at, 'avast', avast FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, updated_at, 'avast_mobile', avast_mobile FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, updated_at, 'bitdefender', bitdefender FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, updated_at, 'bitdefenderfalx', bitdefenderfalx FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, updated_at, 'ikarus', ikarus FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, updated_at, 'k7gw', k7gw FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, updated_at, 'kaspersky', kaspersky FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, updated_at, 'lionic', lionic FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, updated_at, 'microsoft', microsoft FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, updated_at, 'tencent', tencent FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, updated_at, 'zonealarm', zonealarm FROM virustotal_sample_vendor_engine_verdicts
),
vendor_clean AS (
    SELECT
        vl.sample_id,
        vl.source_report_date_utc,
        LOWER(TRIM(vl.vendor_key)) AS vendor_key,
        TRIM(vl.raw_vendor_label) AS raw_vendor_label
    FROM vendor_long AS vl
    WHERE vl.raw_vendor_label IS NOT NULL
      AND TRIM(vl.raw_vendor_label) <> ''
      AND LOWER(TRIM(vl.raw_vendor_label)) NOT IN (
          'none',
          'null',
          'n/a',
          'undetected',
          'clean',
          'benign',
          'harmless',
          'safe',
          'approved',
          'verified',
          'type-unsupported',
          'type_unsupported',
          'timeout',
          'failure'
      )
)
SELECT
    vc.sample_id,
    vc.vendor_key,
    vc.raw_vendor_label,
    NULL AS parsed_family_token,
    NULL AS parsed_type_token,
    NULL AS parsed_class_token,
    0 AS generic_token_flag,
    'wide_vt_seed' AS parser_name,
    'seed_v1' AS parser_version,
    NULL AS parser_confidence_score,
    vc.source_report_date_utc,
    1 AS is_active,
    'seeded from wide virustotal_sample_vendor_engine_verdicts table before parser enrichment' AS notes
FROM vendor_clean AS vc
LEFT JOIN malware_family_label_evidence AS e
    ON e.evidence_identity_sha1 = SHA1(
        CONCAT_WS(
            '|',
            CAST(vc.sample_id AS CHAR),
            COALESCE(vc.vendor_key, ''),
            COALESCE(vc.raw_vendor_label, ''),
            'wide_vt_seed',
            'seed_v1',
            COALESCE(CAST(vc.source_report_date_utc AS CHAR), ''),
            '1'
        )
    )
WHERE e.evidence_id IS NULL;

-- Optional sanity snapshot after seed.
SELECT
    vendor_key,
    COUNT(*) AS seeded_rows,
    COUNT(DISTINCT sample_id) AS distinct_samples
FROM malware_family_label_evidence
WHERE parser_name = 'wide_vt_seed'
  AND is_active = 1
GROUP BY vendor_key
ORDER BY seeded_rows DESC, vendor_key ASC;
