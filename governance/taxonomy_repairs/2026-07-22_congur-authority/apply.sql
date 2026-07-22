-- Approved 2026-07-22. This update must affect exactly one existing bootstrap row.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET primary_type_id = 4,
    family_status = 'active',
        is_active = 1,
        canonical_source_name = 'NHS Digital Congur Android Ransomware',
        canonical_source_url = 'https://digital.nhs.uk/cyber-alerts/2018/cc-2039',
        review_reason = 'research_backed_authority_curation',
        review_source_name = 'NHS Congur PIN-lock ransomware; Kaspersky Q1',
        reviewed_at_utc = UTC_TIMESTAMP()
WHERE family_id = 356
  AND family_slug = 'congur'
  AND family_status = 'needs_review'
  AND is_active = 0
  AND primary_type_id = 8
  AND canonical_source_name IS NULL
  AND canonical_source_url IS NULL
  AND normalization_target_family_id IS NULL;

SELECT ROW_COUNT() AS expected_one_updated_row;
COMMIT;
