-- All statements are read-only and return aggregate or taxonomy metadata only.
SELECT family_id, family_slug, family_status, is_active, primary_type_id,
       canonical_source_name, canonical_source_url, review_reason,
       review_source_name, normalization_target_family_id
FROM erebus_threat_intel_prod.android_malware_family WHERE family_id = 260;

SELECT COUNT(DISTINCT m.sample_id) AS catalog_mapped_samples,
       COUNT(DISTINCT a.sample_id) AS authority_samples,
       COUNT(*) AS authority_rows, SUM(a.family_id = 260) AS rows_mapped_to_family_260
FROM erebus_threat_intel_prod.malware_sample_family_mapping AS m
LEFT JOIN erebus_threat_intel_prod.v_android_sample_family_type_authority AS a ON a.sample_id = m.sample_id
WHERE m.family_id = 260;

SELECT 'active_aliases_on_inactive_families' AS check_name, COUNT(*) AS finding_count
FROM erebus_threat_intel_prod.android_malware_family_alias AS a
JOIN erebus_threat_intel_prod.android_malware_family AS f ON f.family_id = a.family_id
WHERE a.is_active = 1 AND f.is_active = 0
UNION ALL
SELECT 'active_normalized_alias_collisions', COUNT(*) FROM (
 SELECT LOWER(TRIM(alias_name)) AS normalized_alias FROM erebus_threat_intel_prod.android_malware_family_alias
 WHERE is_active = 1 GROUP BY LOWER(TRIM(alias_name)) HAVING COUNT(DISTINCT family_id) > 1
) AS collisions
UNION ALL
SELECT 'authority_view_duplicate_sample_groups', COUNT(*) FROM (
 SELECT sample_id FROM erebus_threat_intel_prod.v_android_sample_family_type_authority
 GROUP BY sample_id HAVING COUNT(*) > 1
) AS duplicate_groups;
