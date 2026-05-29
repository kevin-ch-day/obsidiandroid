-- Read-only worklist for Android + PI-observed rows where the package identity
-- looks more like a legitimate public app / provenance-drift issue than a safe
-- malware-label backfill target.

SET NAMES utf8mb4;

WITH
pi AS (
    SELECT DISTINCT sample_id
    FROM android_permission_intel.android_permission_obs_sample
),
package_catalog_stats AS (
    SELECT
        android_package_name,
        COUNT(*) AS catalog_rows_for_package,
        SUM(CASE WHEN COALESCE(TRIM(classification_primary), '') <> '' THEN 1 ELSE 0 END) AS labeled_catalog_rows_for_package,
        COUNT(
            DISTINCT CASE
                WHEN COALESCE(TRIM(classification_primary), '') <> ''
                THEN CONCAT(classification_primary, '||', COALESCE(classification_subtype, ''))
                ELSE NULL
            END
        ) AS distinct_catalog_labels_for_package
    FROM malware_sample_catalog
    WHERE android_package_name IN (
        'com.ubnt.easyunifi',
        'net.telewebion',
        'by.lsdsl.hdrezka',
        'com.learn.toppr'
    )
    GROUP BY android_package_name
)
SELECT
    msc.sample_id,
    msc.sha256,
    msc.android_package_name,
    msc.source_batch_label,
    COALESCE(vs.confidence_bucket, 'none') AS confidence_bucket,
    COALESCE(vs.confidence_score, 0) AS confidence_score,
    COALESCE(pcs.catalog_rows_for_package, 0) AS catalog_rows_for_package,
    COALESCE(pcs.labeled_catalog_rows_for_package, 0) AS labeled_catalog_rows_for_package,
    COALESCE(pcs.distinct_catalog_labels_for_package, 0) AS distinct_catalog_labels_for_package,
    'likely_legit_package_identity_review' AS remediation_lane,
    CASE
        WHEN COALESCE(pcs.catalog_rows_for_package, 0) >= 10
            THEN 'High-repeat public package identity in the malware catalog; review provenance and consider catalog exclusion before malware labeling.'
        ELSE 'Review likely legit/public package identity, provenance, and catalog fit before any malware labeling.'
    END AS remediation_note
FROM malware_sample_catalog AS msc
JOIN pi
  ON pi.sample_id = msc.sample_id
LEFT JOIN v_android_sample_family_type_authority AS a
  ON a.sample_id = msc.sample_id
LEFT JOIN vt_sample_verdict_confidence_current AS vs
  ON vs.sample_id = msc.sample_id
LEFT JOIN package_catalog_stats AS pcs
  ON pcs.android_package_name = msc.android_package_name
WHERE LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
  AND COALESCE(TRIM(msc.classification_primary), '') = ''
  AND COALESCE(TRIM(msc.family_label), '') = ''
  AND COALESCE(a.authority_bucket, '<none>') = 'missing_resolved_family'
  AND msc.android_package_name IN (
      'com.ubnt.easyunifi',
      'net.telewebion',
      'by.lsdsl.hdrezka',
      'com.learn.toppr'
  )
ORDER BY
    msc.android_package_name,
    msc.sample_id;
