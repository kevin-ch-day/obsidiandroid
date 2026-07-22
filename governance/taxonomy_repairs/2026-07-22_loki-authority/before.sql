-- Contemporaneous pre-change capture. Execute before apply.sql.
SELECT f.family_id, f.family_name, f.family_slug, f.family_status, f.is_active,
       f.primary_type_id, t.type_slug AS primary_type_slug,
       f.canonical_source_name, f.canonical_source_url, f.review_reason,
       f.review_source_name, f.reviewed_at_utc, f.normalization_target_family_id
FROM erebus_threat_intel_prod.android_malware_family AS f
LEFT JOIN erebus_threat_intel_prod.android_malware_type AS t ON t.type_id = f.primary_type_id
WHERE f.family_id = 461;

SELECT COUNT(*) AS mapping_rows, COUNT(DISTINCT sample_id) AS distinct_mapped_samples,
       SUM(review_status = 'family_under_review') AS family_under_review_rows
FROM erebus_threat_intel_prod.malware_sample_family_mapping WHERE family_id = 461;

SELECT
    (SELECT COUNT(*) FROM erebus_threat_intel_prod.android_malware_family_alias WHERE family_id = 461) AS alias_rows,
    (SELECT COUNT(*) FROM erebus_threat_intel_prod.android_malware_family_alias WHERE family_id = 461 AND is_active = 1) AS active_alias_rows,
    (SELECT COUNT(*) FROM erebus_threat_intel_prod.v_android_sample_family_type_authority WHERE family_id = 461) AS authority_rows,
    (SELECT COUNT(*) FROM (
      SELECT LOWER(TRIM(family_slug)) AS token FROM erebus_threat_intel_prod.android_malware_family WHERE is_active = 1 AND family_id <> 461
      UNION ALL SELECT LOWER(TRIM(alias_name)) FROM erebus_threat_intel_prod.android_malware_family_alias WHERE is_active = 1
    ) AS active_tokens WHERE token = 'loki') AS active_slug_or_alias_collisions;
