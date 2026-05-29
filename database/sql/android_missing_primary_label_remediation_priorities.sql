-- Prioritized remediation worklist for Android + PI-observed rows that still
-- have blank `classification_primary`.
--
-- Purpose:
--   - split the remaining backlog into actionable remediation lanes
--   - distinguish label-now candidates from false-positive/provenance review
--   - keep residual `Unknown` family rows separate from blank-family reservoir
--
-- This is a read-only operator worklist.

SET NAMES utf8mb4;

DROP TEMPORARY TABLE IF EXISTS tmp_android_missing_primary_label_prioritized;

CREATE TEMPORARY TABLE tmp_android_missing_primary_label_prioritized AS
WITH
pi AS (
    SELECT DISTINCT sample_id
    FROM android_permission_intel.android_permission_obs_sample
),
gap AS (
    SELECT
        msc.sample_id,
        msc.sha256,
        msc.android_package_name,
        msc.source_batch_label,
        COALESCE(NULLIF(TRIM(msc.family_label), ''), '<blank>') AS family_label_raw,
        COALESCE(a.authority_bucket, '<none>') AS authority_bucket,
        COALESCE(a.authority_gap_reason, '<none>') AS authority_gap_reason,
        COALESCE(vs.confidence_bucket, 'none') AS confidence_bucket,
        COALESCE(vs.confidence_score, 0) AS confidence_score
    FROM malware_sample_catalog AS msc
    JOIN pi
      ON pi.sample_id = msc.sample_id
    LEFT JOIN v_android_sample_family_type_authority AS a
      ON a.sample_id = msc.sample_id
    LEFT JOIN vt_sample_verdict_confidence_current AS vs
      ON vs.sample_id = msc.sample_id
    WHERE LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
      AND COALESCE(TRIM(msc.classification_primary), '') = ''
)
SELECT
    g.*,
    CASE
        WHEN g.sample_id = 32521 THEN 'candidate_pua_manual_confirm'
        WHEN g.sample_id = 31128 THEN 'possible_false_positive_or_package_reuse'
        WHEN g.authority_bucket = 'missing_resolved_family'
             AND g.android_package_name IN ('com.ubnt.easyunifi', 'net.telewebion', 'by.lsdsl.hdrezka', 'com.learn.toppr')
             THEN 'likely_legit_package_identity_review'
        WHEN g.authority_bucket = 'missing_resolved_family'
             AND g.confidence_score = 0 THEN 'likely_false_positive_or_provenance_review'
        WHEN g.authority_bucket = 'resolved_unknown'
             AND g.confidence_bucket IN ('high', 'strong') THEN 'unknown_family_manual_label_review'
        WHEN g.authority_bucket = 'resolved_unknown' THEN 'unknown_family_low_signal_review'
        ELSE 'other_manual_review'
    END AS remediation_lane,
    CASE
        WHEN g.sample_id = 32521 THEN 'High'
        WHEN g.sample_id = 31128 THEN 'High'
        WHEN g.authority_bucket = 'missing_resolved_family'
             AND g.android_package_name IN ('com.ubnt.easyunifi', 'net.telewebion', 'by.lsdsl.hdrezka', 'com.learn.toppr')
             THEN 'High'
        WHEN g.authority_bucket = 'missing_resolved_family'
             AND g.confidence_score = 0 THEN 'High'
        WHEN g.authority_bucket = 'resolved_unknown'
             AND g.confidence_bucket IN ('high', 'strong') THEN 'Medium'
        ELSE 'Low'
    END AS remediation_priority,
    CASE
        WHEN g.sample_id = 32521 THEN 'Package matches public Your Freedom app listing; detections look clone/PUP-like, not family-attribution-ready.'
        WHEN g.sample_id = 31128 THEN 'Package name is heavily reused on third-party APK sites; weak VT signal suggests package/provenance review before labeling.'
        WHEN g.authority_bucket = 'missing_resolved_family'
             AND g.android_package_name IN ('com.ubnt.easyunifi', 'net.telewebion', 'by.lsdsl.hdrezka', 'com.learn.toppr')
             THEN 'Package matches a public app identity strongly enough that this row should be reviewed as likely legit / provenance drift before any malware labeling.'
        WHEN g.authority_bucket = 'missing_resolved_family'
             AND g.confidence_score = 0 THEN 'Blank-family reservoir row with no current VT confidence; route to false-positive/provenance queue before malware labeling.'
        WHEN g.authority_bucket = 'resolved_unknown'
             AND g.confidence_bucket IN ('high', 'strong') THEN 'High-signal Android row still lacks trustworthy family truth; requires manual malware label adjudication.'
        WHEN g.authority_bucket = 'resolved_unknown' THEN 'Low-signal unknown-family row; keep behind higher-yield remediation work.'
        ELSE 'Manual review required.'
    END AS remediation_note
FROM gap AS g;

SELECT
    remediation_priority,
    remediation_lane,
    COUNT(*) AS rows_in_lane
FROM tmp_android_missing_primary_label_prioritized
GROUP BY remediation_priority, remediation_lane
ORDER BY
    FIELD(remediation_priority, 'High', 'Medium', 'Low'),
    rows_in_lane DESC,
    remediation_lane;

SELECT
    sample_id,
    android_package_name,
    source_batch_label,
    family_label_raw,
    authority_bucket,
    authority_gap_reason,
    confidence_bucket,
    confidence_score,
    remediation_priority,
    remediation_lane,
    remediation_note
FROM tmp_android_missing_primary_label_prioritized
ORDER BY
    FIELD(remediation_priority, 'High', 'Medium', 'Low'),
    confidence_score DESC,
    sample_id;
