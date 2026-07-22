-- Exact rollback of the approved primary-type remap and review fields only.
-- Review post-change evidence before executing.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET primary_type_id = 10,
    review_reason = 'curated_import',
    review_source_name = 'obsidiandroid',
    reviewed_at_utc = '2026-05-25 10:48:58'
WHERE family_id = 85
  AND family_slug = 'smsworm'
  AND family_status = 'active'
  AND is_active = 1
  AND primary_type_id = 14
  AND review_reason = 'research_backed_authority_curation'
  AND normalization_target_family_id IS NULL;

SELECT ROW_COUNT() AS expected_one_restored_row;
COMMIT;
