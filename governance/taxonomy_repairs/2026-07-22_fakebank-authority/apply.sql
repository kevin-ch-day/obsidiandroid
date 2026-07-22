-- Approved 2026-07-22. This update must affect exactly one existing bootstrap row.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET family_status = 'active',
        is_active = 1,
        canonical_source_name = 'Trend Micro FakeBank SMS banking theft',
        canonical_source_url = 'https://gbhackers.com/fakebank-malware-layered-obfuscation-technique/',
        review_reason = 'research_backed_authority_curation',
        review_source_name = 'Trend Micro FakeBank SMS banking interception',
        reviewed_at_utc = UTC_TIMESTAMP()
WHERE family_id = 385
  AND family_slug = 'fakebank'
  AND family_status = 'needs_review'
  AND is_active = 0
  AND primary_type_id = 12
  AND canonical_source_name IS NULL
  AND canonical_source_url IS NULL
  AND normalization_target_family_id IS NULL;

SELECT ROW_COUNT() AS expected_one_updated_row;
COMMIT;
