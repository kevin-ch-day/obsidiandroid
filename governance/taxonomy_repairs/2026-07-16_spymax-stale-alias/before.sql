-- Read-only identity capture for a backfilled receipt.
-- Limitation: the historical before-state was reconstructed from recorded
-- terminal query output; this query returns the current post-change row only.
SELECT
    a.alias_id,
    a.alias_name,
    a.family_id,
    a.is_active AS alias_is_active,
    a.is_preferred,
    a.review_status,
    a.confidence,
    f.family_status,
    f.is_active AS family_is_active,
    f.normalization_target_family_id
FROM erebus_threat_intel_prod.android_malware_family_alias AS a
JOIN erebus_threat_intel_prod.android_malware_family AS f
  ON f.family_id = a.family_id
WHERE a.alias_id = 183;
