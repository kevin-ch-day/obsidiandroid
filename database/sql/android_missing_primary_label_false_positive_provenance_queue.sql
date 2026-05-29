-- Read-only worklist for blank-family Android + PI-observed rows that are more
-- likely false-positive / provenance drift than safe malware-label backfill.

SET NAMES utf8mb4;

WITH
pi AS (
    SELECT DISTINCT sample_id
    FROM android_permission_intel.android_permission_obs_sample
)
SELECT
    msc.sample_id,
    msc.android_package_name,
    msc.source_batch_label,
    COALESCE(vs.confidence_bucket, 'none') AS confidence_bucket,
    COALESCE(vs.confidence_score, 0) AS confidence_score,
    'likely_false_positive_or_provenance_review' AS remediation_lane,
    'Review package provenance, signer/source reuse, and whether the row belongs in the malware catalog at all.' AS remediation_note
FROM malware_sample_catalog AS msc
JOIN pi
  ON pi.sample_id = msc.sample_id
LEFT JOIN v_android_sample_family_type_authority AS a
  ON a.sample_id = msc.sample_id
LEFT JOIN vt_sample_verdict_confidence_current AS vs
  ON vs.sample_id = msc.sample_id
WHERE LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
  AND COALESCE(TRIM(msc.classification_primary), '') = ''
  AND COALESCE(TRIM(msc.family_label), '') = ''
  AND COALESCE(a.authority_bucket, '<none>') = 'missing_resolved_family'
  AND COALESCE(vs.confidence_score, 0) = 0
ORDER BY
    msc.android_package_name,
    msc.sample_id;
