-- Exact rollback of the applied family-state fields only. Review evidence first.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET family_status = 'needs_review',
    is_active = 0,
    canonical_source_name = NULL,
    canonical_source_url = NULL,
    review_reason = 'lamda_catalog_gap_bootstrap',
    review_source_name = NULL,
    reviewed_at_utc = NULL
WHERE family_id = 268
  AND family_slug = 'jsmshider'
  AND family_status = 'active'
  AND is_active = 1
  AND primary_type_id = 14
  AND canonical_source_name = 'Microsoft Security Intelligence'
  AND review_reason = 'research_backed_authority_curation';

SELECT ROW_COUNT() AS expected_one_restored_row;
COMMIT;
