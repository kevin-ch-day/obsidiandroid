-- Approved 2026-07-17. This update must affect exactly one existing bootstrap row.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET primary_type_id = 6,
    family_status = 'active',
    is_active = 1,
    canonical_source_name = 'Bitdefender',
    canonical_source_url = 'https://www.bitdefender.com/en-gb/blog/hotforsecurity/from-china-with-love-new-android-backdoor-spreading-through-hacked-apps',
    review_reason = 'research_backed_authority_curation',
    review_source_name = 'Bitdefender; AMD 2017 Android malware dataset paper',
    reviewed_at_utc = UTC_TIMESTAMP()
WHERE family_id = 261
  AND family_slug = 'fakeangry'
  AND family_status = 'needs_review'
  AND is_active = 0
  AND primary_type_id = 8
  AND canonical_source_name IS NULL
  AND canonical_source_url IS NULL
  AND normalization_target_family_id IS NULL;

SELECT ROW_COUNT() AS expected_one_updated_row;
COMMIT;
