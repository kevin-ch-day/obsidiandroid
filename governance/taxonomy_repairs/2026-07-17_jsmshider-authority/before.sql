-- Read-only identity capture for a backfilled receipt.
-- Limitation: historical before-state values are reconstructed from recorded
-- terminal query output; this query returns the current post-change row only.
SELECT
    family_id,
    family_name,
    family_slug,
    family_status,
    is_active,
    primary_type_id,
    canonical_source_name,
    canonical_source_url,
    review_reason,
    review_source_name,
    reviewed_at_utc,
    normalization_target_family_id
FROM erebus_threat_intel_prod.android_malware_family
WHERE family_id = 268;
