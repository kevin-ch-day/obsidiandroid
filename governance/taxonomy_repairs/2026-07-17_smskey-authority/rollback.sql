-- Exact rollback of the approved family-state and source fields only.
-- Review post-change evidence before executing.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET family_status = 'needs_review', is_active = 0,
    canonical_source_name = NULL, canonical_source_url = NULL,
    review_reason = 'lamda_catalog_gap_bootstrap', review_source_name = NULL,
    reviewed_at_utc = NULL
WHERE family_id = 274
  AND family_slug = 'smskey'
  AND family_status = 'active'
  AND is_active = 1
  AND primary_type_id = 14
  AND canonical_source_name = 'Argus Lab Android Malware Dataset'
  AND canonical_source_url = 'https://amd.arguslab.org/families/SmsKey/variety1.html'
  AND review_reason = 'research_backed_authority_curation'
  AND normalization_target_family_id IS NULL;

SELECT ROW_COUNT() AS expected_one_restored_row;
COMMIT;
