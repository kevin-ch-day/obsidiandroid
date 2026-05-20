-- Smoke-check the label authority foundation objects after deployment.
--
-- Run after:
--   1. label_authority_foundation.sql
--   2. optional backfill via label_authority_backfill.sql

SET NAMES utf8mb4;

SELECT
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
      'malware_family_alias_fact',
      'malware_family_authority_fact',
      'vendor_label_generic_token_fact',
      'av_engine_dependency_fact',
      'malware_family_label_evidence',
      'v_android_sample_temporal_resolved',
      'label_authority_resolution_view'
  )
ORDER BY table_name ASC;

SELECT
    'malware_family_alias_fact' AS object_name,
    COUNT(*) AS row_count,
    COUNT(DISTINCT canonical_family_slug) AS distinct_canonical_family_slug
FROM malware_family_alias_fact
UNION ALL
SELECT
    'malware_family_authority_fact' AS object_name,
    COUNT(*) AS row_count,
    COUNT(DISTINCT governed_family_slug) AS distinct_canonical_family_slug
FROM malware_family_authority_fact
UNION ALL
SELECT
    'malware_family_label_evidence' AS object_name,
    COUNT(*) AS row_count,
    COUNT(DISTINCT parsed_family_token) AS distinct_canonical_family_slug
FROM malware_family_label_evidence;

SELECT
    temporal_anchor_source,
    temporal_anchor_quality,
    COUNT(*) AS n_samples
FROM v_android_sample_temporal_resolved
GROUP BY temporal_anchor_source, temporal_anchor_quality
ORDER BY n_samples DESC, temporal_anchor_source ASC;

SELECT
    explicit_authority_override_flag,
    COUNT(*) AS n_samples
FROM label_authority_resolution_view
GROUP BY explicit_authority_override_flag
ORDER BY explicit_authority_override_flag DESC;

SELECT
    COUNT(*) AS rows_missing_effective_family_slug
FROM label_authority_resolution_view
WHERE COALESCE(TRIM(effective_family_slug), '') = '';

SELECT
    COUNT(*) AS rows_missing_effective_type_slug
FROM label_authority_resolution_view
WHERE COALESCE(TRIM(effective_type_slug), '') = '';
