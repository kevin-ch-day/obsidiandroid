-- Exact rollback of the applied field only. Review current evidence before use.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family_alias AS a
JOIN erebus_threat_intel_prod.android_malware_family AS f
  ON f.family_id = a.family_id
SET a.is_active = 1
WHERE a.alias_id = 183
  AND LOWER(TRIM(a.alias_name)) = 'spymax'
  AND a.is_active = 0
  AND a.is_preferred = 1
  AND f.family_id = 37
  AND f.is_active = 0
  AND f.normalization_target_family_id = 36;

SELECT ROW_COUNT() AS expected_one_restored_row;
COMMIT;
