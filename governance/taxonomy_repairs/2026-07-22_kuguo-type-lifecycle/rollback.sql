-- Exact rollback of the approved primary-type remap and review fields only.
-- Review post-change evidence before executing.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET primary_type_id = 19,
    review_reason = NULL,
    review_source_name = NULL,
    reviewed_at_utc = NULL
WHERE family_id = 80
  AND family_slug = 'kuguo'
  AND family_status = 'active'
  AND is_active = 1
  AND primary_type_id = 3
  AND review_reason = 'research_backed_authority_curation'
  AND normalization_target_family_id IS NULL;

SELECT ROW_COUNT() AS expected_one_restored_row;
COMMIT;
