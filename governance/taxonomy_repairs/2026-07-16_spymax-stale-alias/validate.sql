-- All statements are read-only and return aggregate or taxonomy metadata only.
SELECT a.alias_id, a.alias_name, a.family_id, a.is_active, a.is_preferred,
       f.family_status, f.is_active AS family_is_active,
       f.normalization_target_family_id,
       (SELECT COUNT(*)
          FROM erebus_threat_intel_prod.malware_sample_family_mapping
         WHERE family_id = 37) AS historical_mapping_count
FROM erebus_threat_intel_prod.android_malware_family_alias AS a
JOIN erebus_threat_intel_prod.android_malware_family AS f
  ON f.family_id = a.family_id
WHERE a.alias_id = 183;

SELECT 'active_aliases_on_inactive_families' AS check_name, COUNT(*) AS finding_count
FROM erebus_threat_intel_prod.android_malware_family_alias AS a
JOIN erebus_threat_intel_prod.android_malware_family AS f
  ON f.family_id = a.family_id
WHERE a.is_active = 1 AND f.is_active = 0
UNION ALL
SELECT 'active_normalized_alias_collisions', COUNT(*)
FROM (
    SELECT LOWER(TRIM(alias_name)) AS normalized_alias
    FROM erebus_threat_intel_prod.android_malware_family_alias
    WHERE is_active = 1
    GROUP BY LOWER(TRIM(alias_name))
    HAVING COUNT(DISTINCT family_id) > 1
) AS collisions
UNION ALL
SELECT 'resolved_view_duplicate_sample_groups', COUNT(*)
FROM (
    SELECT sample_id
    FROM erebus_threat_intel_prod.v_android_apk_family_resolved
    GROUP BY sample_id
    HAVING COUNT(*) > 1
) AS duplicate_groups
UNION ALL
SELECT 'authority_view_duplicate_sample_groups', COUNT(*)
FROM (
    SELECT sample_id
    FROM erebus_threat_intel_prod.v_android_sample_family_type_authority
    GROUP BY sample_id
    HAVING COUNT(*) > 1
) AS duplicate_groups;
