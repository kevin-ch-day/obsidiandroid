-- Approved 2026-07-17. This update must affect exactly one existing bootstrap row.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET primary_type_id = 1,
    family_status = 'active',
    is_active = 1,
    canonical_source_name = 'K7 Labs',
    canonical_source_url = 'https://labs.k7computing.com/index.php/paranoid-android-part-2/',
    review_reason = 'research_backed_authority_curation',
    review_source_name = 'K7 Labs; UCR malicious Android-app characterization',
    reviewed_at_utc = UTC_TIMESTAMP()
WHERE family_id = 260
  AND family_slug = 'droiddreamlight'
  AND family_status = 'needs_review'
  AND is_active = 0
  AND primary_type_id = 8
  AND canonical_source_name IS NULL
  AND canonical_source_url IS NULL
  AND normalization_target_family_id IS NULL;

SELECT ROW_COUNT() AS expected_one_updated_row;
COMMIT;
