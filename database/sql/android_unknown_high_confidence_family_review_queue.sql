-- Read-only worklist for Android + PI-observed rows where the catalog family is
-- still `Unknown` but VT confidence is already high/strong.

SET NAMES utf8mb4;

WITH
pi AS (
    SELECT DISTINCT sample_id
    FROM android_permission_intel.android_permission_obs_sample
),
labeled_siblings AS (
    SELECT
        android_package_name,
        COUNT(*) AS labeled_sibling_rows,
        COUNT(DISTINCT CONCAT(classification_primary, '||', COALESCE(classification_subtype, ''))) AS distinct_label_count,
        MIN(classification_primary) AS sibling_primary_hint,
        MIN(classification_subtype) AS sibling_subtype_hint
    FROM malware_sample_catalog
    WHERE LOWER(TRIM(COALESCE(platform, ''))) = 'android'
      AND COALESCE(TRIM(classification_primary), '') <> ''
    GROUP BY android_package_name
)
SELECT
    msc.sample_id,
    msc.android_package_name,
    COALESCE(vs.confidence_bucket, 'none') AS confidence_bucket,
    COALESCE(vs.confidence_score, 0) AS confidence_score,
    COALESCE(ls.labeled_sibling_rows, 0) AS labeled_sibling_rows,
    COALESCE(ls.distinct_label_count, 0) AS sibling_distinct_label_count,
    ls.sibling_primary_hint,
    ls.sibling_subtype_hint,
    CASE
        WHEN COALESCE(ls.labeled_sibling_rows, 0) > 0 AND COALESCE(ls.distinct_label_count, 0) = 1
            THEN 'candidate_same_package_label_review'
        ELSE 'manual_unknown_family_review'
    END AS remediation_lane
FROM malware_sample_catalog AS msc
JOIN pi
  ON pi.sample_id = msc.sample_id
LEFT JOIN v_android_sample_family_type_authority AS a
  ON a.sample_id = msc.sample_id
LEFT JOIN vt_sample_verdict_confidence_current AS vs
  ON vs.sample_id = msc.sample_id
LEFT JOIN labeled_siblings AS ls
  ON ls.android_package_name = msc.android_package_name
WHERE LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
  AND COALESCE(TRIM(msc.classification_primary), '') = ''
  AND LOWER(TRIM(COALESCE(msc.family_label, ''))) = 'unknown'
  AND COALESCE(a.authority_bucket, '<none>') = 'resolved_unknown'
  AND COALESCE(vs.confidence_bucket, 'none') IN ('high', 'strong')
ORDER BY
    COALESCE(vs.confidence_score, 0) DESC,
    COALESCE(ls.labeled_sibling_rows, 0) DESC,
    msc.sample_id;
