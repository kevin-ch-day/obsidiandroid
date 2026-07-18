-- Approved 2026-07-17. This update must affect exactly one existing bootstrap row.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET family_status = 'active',
    is_active = 1,
    canonical_source_name = 'Check Point Research',
    canonical_source_url = 'https://research.checkpoint.com/2019/simbad-a-rogue-adware-campaign-on-google-play/',
    review_reason = 'research_backed_authority_curation',
    review_source_name = 'Check Point Research; MITRE ATT&CK',
    reviewed_at_utc = UTC_TIMESTAMP()
WHERE family_id = 290
  AND family_slug = 'simbad'
  AND family_status = 'needs_review'
  AND is_active = 0
  AND primary_type_id = 3
  AND canonical_source_name IS NULL
  AND canonical_source_url IS NULL
  AND normalization_target_family_id IS NULL;

SELECT ROW_COUNT() AS expected_one_updated_row;
COMMIT;
