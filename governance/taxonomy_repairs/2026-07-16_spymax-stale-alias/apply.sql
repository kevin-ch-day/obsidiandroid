-- Applied 2026-07-16. The update must affect exactly one row.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family_alias AS a
JOIN erebus_threat_intel_prod.android_malware_family AS f
  ON f.family_id = a.family_id
JOIN erebus_threat_intel_prod.android_malware_family AS target
  ON target.family_id = f.normalization_target_family_id
SET a.is_active = 0
WHERE a.alias_id = 183
  AND LOWER(TRIM(a.alias_name)) = 'spymax'
  AND a.is_active = 1
  AND f.is_active = 0
  AND f.normalization_target_family_id = 36
  AND target.is_active = 1;

SELECT ROW_COUNT() AS expected_one_updated_row;
COMMIT;
