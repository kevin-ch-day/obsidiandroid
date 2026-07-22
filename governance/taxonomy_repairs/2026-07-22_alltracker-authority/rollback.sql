-- Exact rollback of the approved fields only.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET primary_type_id = 8,
    family_status = 'needs_review',
        is_active = 0,
        canonical_source_name = NULL,
        canonical_source_url = NULL,
        review_reason = 'lamda_catalog_gap_bootstrap',
        review_source_name = NULL,
        reviewed_at_utc = NULL
WHERE family_id = 326
  AND family_slug = 'alltracker'
  AND family_status = 'active'
  AND is_active = 1
  AND primary_type_id = 17
  AND review_reason = 'research_backed_authority_curation'
  AND normalization_target_family_id IS NULL;

SELECT ROW_COUNT() AS expected_one_restored_row;
COMMIT;
