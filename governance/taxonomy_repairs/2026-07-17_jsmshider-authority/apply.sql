-- Applied 2026-07-17. The update must affect exactly one existing bootstrap row.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET family_status = 'active',
    is_active = 1,
    canonical_source_name = 'Microsoft Security Intelligence',
    canonical_source_url = 'https://www.microsoft.com/en-us/wdsi/threats/malware-encyclopedia-description?Name=Trojan%3AAndroidOS%2FSmsHider.A',
    review_reason = 'research_backed_authority_curation',
    review_source_name = 'Microsoft Security Intelligence; Android malware research',
    reviewed_at_utc = UTC_TIMESTAMP()
WHERE family_id = 268
  AND family_slug = 'jsmshider'
  AND family_status = 'needs_review'
  AND is_active = 0
  AND primary_type_id = 14;

SELECT ROW_COUNT() AS expected_one_updated_row;
COMMIT;
