-- Approved 2026-07-22. Remap one active family off a retired primary type.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET primary_type_id = 3,
    review_reason = 'research_backed_authority_curation',
    review_source_name = 'Dr.Web Adware.Kuguo; AMD 2017; SANER 2019; MS PUA/Kuguo',
    reviewed_at_utc = UTC_TIMESTAMP()
WHERE family_id = 80
  AND family_slug = 'kuguo'
  AND family_status = 'active'
  AND is_active = 1
  AND primary_type_id = 19
  AND canonical_source_name = 'Microsoft Security Intelligence'
  AND normalization_target_family_id IS NULL;

SELECT ROW_COUNT() AS expected_one_updated_row;
COMMIT;
