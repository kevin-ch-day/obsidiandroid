-- Approved 2026-07-22. This update must affect exactly one existing bootstrap row.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET family_status = 'active',
        is_active = 1,
        canonical_source_name = 'CIC AndMal2020',
        canonical_source_url = 'https://www.unb.ca/cic/datasets/andmal2020.html',
        review_reason = 'research_backed_authority_curation',
        review_source_name = 'AndMal2020 StopSMS; KronoDroid Airpush/StopSMS',
        reviewed_at_utc = UTC_TIMESTAMP()
WHERE family_id = 285
  AND family_slug = 'stopsms'
  AND family_status = 'needs_review'
  AND is_active = 0
  AND primary_type_id = 14
  AND canonical_source_name IS NULL
  AND canonical_source_url IS NULL
  AND normalization_target_family_id IS NULL;

SELECT ROW_COUNT() AS expected_one_updated_row;
COMMIT;
