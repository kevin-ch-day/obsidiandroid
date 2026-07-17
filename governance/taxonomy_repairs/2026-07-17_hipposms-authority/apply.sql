-- Approved 2026-07-17. This update must affect exactly one existing bootstrap row.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET family_status = 'active',
    is_active = 1,
    canonical_source_name = 'F-Secure Threat Descriptions',
    canonical_source_url = 'https://www.f-secure.com/v-descs/trojan-android-hipposms',
    review_reason = 'research_backed_authority_curation',
    review_source_name = 'F-Secure Threat Descriptions; CCCS-CIC-AndMal-2020',
    reviewed_at_utc = UTC_TIMESTAMP()
WHERE family_id = 257
  AND family_slug = 'hipposms'
  AND family_status = 'needs_review'
  AND is_active = 0
  AND primary_type_id = 14
  AND canonical_source_name IS NULL
  AND canonical_source_url IS NULL
  AND normalization_target_family_id IS NULL;

SELECT ROW_COUNT() AS expected_one_updated_row;
COMMIT;
