-- Approved 2026-07-17. This update must affect exactly one existing bootstrap row.
START TRANSACTION;

UPDATE erebus_threat_intel_prod.android_malware_family
SET primary_type_id=1,
    family_status='active', is_active=1,
    canonical_source_name='McAfee Threats Report',
    canonical_source_url='https://med.a51.nl/sites/default/files/pdf/rp_quarterly_threat_q4_2010.pdf',
    review_reason='research_backed_authority_curation',
    review_source_name='McAfee Threats Report; UCR malicious Android-app characterization',
    reviewed_at_utc=UTC_TIMESTAMP()
WHERE family_id=266 AND family_slug='geinimi' AND family_status='needs_review' AND is_active=0
  AND primary_type_id=8 AND canonical_source_name IS NULL AND canonical_source_url IS NULL
  AND normalization_target_family_id IS NULL;

SELECT ROW_COUNT() AS expected_one_updated_row;
COMMIT;
