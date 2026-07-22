-- Approved 2026-07-22. Remap one active family off a retired primary type.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET primary_type_id = 14,
    review_reason = 'research_backed_authority_curation',
    review_source_name = 'SecurityWeek; F-Secure SMS-Worm; Cyble; sms-trojan peers',
    reviewed_at_utc = UTC_TIMESTAMP()
WHERE family_id = 85
  AND family_slug = 'smsworm'
  AND family_status = 'active'
  AND is_active = 1
  AND primary_type_id = 10
  AND canonical_source_name = 'SecurityWeek'
  AND review_reason = 'curated_import'
  AND normalization_target_family_id IS NULL;

SELECT ROW_COUNT() AS expected_one_updated_row;
COMMIT;
