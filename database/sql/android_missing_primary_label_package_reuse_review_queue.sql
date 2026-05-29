-- Read-only worklist for Android + PI-observed rows where the package identity
-- appears too heavily reused to safely backfill a malware label.

SET NAMES utf8mb4;

SELECT
    m.sample_id,
    m.sha256,
    m.android_package_name,
    COALESCE(vs.confidence_bucket, 'none') AS confidence_bucket,
    COALESCE(vs.confidence_score, 0) AS confidence_score,
    'possible_false_positive_or_package_reuse' AS remediation_lane,
    'Hold malware-label backfill; package identity is reused across unrelated APKs or weakly malicious detections.' AS remediation_note
FROM malware_sample_catalog AS m
JOIN (
    SELECT DISTINCT sample_id
    FROM android_permission_intel.android_permission_obs_sample
) AS pi
  ON pi.sample_id = m.sample_id
LEFT JOIN vt_sample_verdict_confidence_current AS vs
  ON vs.sample_id = m.sample_id
WHERE m.sample_id IN (31128)
  AND LOWER(TRIM(COALESCE(m.platform, ''))) = 'android'
  AND COALESCE(TRIM(m.classification_primary), '') = '';
