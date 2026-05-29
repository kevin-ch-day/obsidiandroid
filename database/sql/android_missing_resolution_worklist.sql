-- Android missing-resolution worklist.
-- Purpose:
--   * isolate rows that still lack any resolved family token
--   * separate package-cluster review from family-authority repair
--   * highlight the few rows with weak VT tails that could bias later curation

-- 1. Current bucket posture
SELECT
  authority_bucket,
  COUNT(*) AS row_count
FROM v_android_sample_family_type_authority
GROUP BY authority_bucket
ORDER BY row_count DESC, authority_bucket;

-- 2. Missing-resolved-family rows by source batch
SELECT
  COALESCE(NULLIF(c.source_batch_label, ''), '<blank>') AS source_batch_label,
  COUNT(*) AS row_count
FROM malware_sample_catalog c
JOIN v_android_sample_family_type_authority a
  ON a.sample_id = c.sample_id
WHERE a.authority_bucket = 'missing_resolved_family'
GROUP BY COALESCE(NULLIF(c.source_batch_label, ''), '<blank>')
ORDER BY row_count DESC, source_batch_label;

-- 3. Missing-resolved-family package clusters
SELECT
  COALESCE(NULLIF(c.android_package_name, ''), '<blank>') AS android_package_name,
  COUNT(*) AS row_count,
  GROUP_CONCAT(c.sample_id ORDER BY c.sample_id) AS sample_ids
FROM malware_sample_catalog c
JOIN v_android_sample_family_type_authority a
  ON a.sample_id = c.sample_id
WHERE a.authority_bucket = 'missing_resolved_family'
GROUP BY COALESCE(NULLIF(c.android_package_name, ''), '<blank>')
ORDER BY row_count DESC, android_package_name;

-- 4. Missing-resolved-family package-prefix clusters
SELECT
  COALESCE(NULLIF(SUBSTRING_INDEX(c.android_package_name, '.', 3), ''), '<blank>') AS package_prefix3,
  COUNT(*) AS row_count,
  GROUP_CONCAT(c.sample_id ORDER BY c.sample_id) AS sample_ids
FROM malware_sample_catalog c
JOIN v_android_sample_family_type_authority a
  ON a.sample_id = c.sample_id
WHERE a.authority_bucket = 'missing_resolved_family'
GROUP BY COALESCE(NULLIF(SUBSTRING_INDEX(c.android_package_name, '.', 3), ''), '<blank>')
ORDER BY row_count DESC, package_prefix3;

-- 5. Detailed missing-resolution rows
SELECT
  c.sample_id,
  c.sha256,
  c.platform,
  c.file_extension,
  c.analysis_lane,
  c.source_batch_label,
  c.android_package_name,
  c.classification_primary,
  c.classification_subtype,
  c.vt_family_token,
  c.vt_suggested_label,
  a.authority_bucket,
  a.authority_gap_reason
FROM malware_sample_catalog c
JOIN v_android_sample_family_type_authority a
  ON a.sample_id = c.sample_id
WHERE a.authority_bucket = 'missing_resolved_family'
ORDER BY c.source_batch_label DESC, c.analysis_lane, c.sample_id;

-- 6. Rows with any VT tail inside missing-resolution bucket
SELECT
  c.sample_id,
  c.sha256,
  c.android_package_name,
  c.analysis_lane,
  c.vt_family_token,
  c.vt_suggested_label,
  CASE
    WHEN LOWER(COALESCE(c.vt_family_token, '')) IN ('jiagu') THEN 'policy_hold_packer'
    WHEN LOWER(COALESCE(c.vt_family_token, '')) IN ('fklz') THEN 'policy_hold_generic'
    WHEN LOWER(COALESCE(c.vt_suggested_label, '')) LIKE '%boogr%' THEN 'policy_hold_generic'
    ELSE 'review'
  END AS vt_tail_disposition
FROM malware_sample_catalog c
JOIN v_android_sample_family_type_authority a
  ON a.sample_id = c.sample_id
WHERE a.authority_bucket = 'missing_resolved_family'
  AND (
    COALESCE(c.vt_family_token, '') <> ''
    OR COALESCE(c.vt_suggested_label, '') <> ''
  )
ORDER BY c.sample_id;

-- 7. Package clusters that are most likely non-taxonomy review items
SELECT
  cluster_type,
  cluster_value,
  row_count,
  sample_ids,
  review_action
FROM (
  SELECT
    'package_name' AS cluster_type,
    COALESCE(NULLIF(c.android_package_name, ''), '<blank>') AS cluster_value,
    COUNT(*) AS row_count,
    GROUP_CONCAT(c.sample_id ORDER BY c.sample_id) AS sample_ids,
    CASE
      WHEN COALESCE(NULLIF(c.android_package_name, ''), '<blank>') = '<blank>' THEN 'inspect_unknown_sparse'
      WHEN c.android_package_name = 'com.ubnt.easyunifi' THEN 'likely_legit_or_repacked_app_cluster'
      WHEN c.android_package_name = 'com.frontrow.vlog' THEN 'inspect_repeated_package_cluster'
      WHEN c.android_package_name = 'net.telewebion' THEN 'inspect_repeated_package_cluster'
      ELSE 'inspect_singleton_package'
    END AS review_action
  FROM malware_sample_catalog c
  JOIN v_android_sample_family_type_authority a
    ON a.sample_id = c.sample_id
  WHERE a.authority_bucket = 'missing_resolved_family'
  GROUP BY COALESCE(NULLIF(c.android_package_name, ''), '<blank>')
) ranked
ORDER BY row_count DESC, cluster_value;
