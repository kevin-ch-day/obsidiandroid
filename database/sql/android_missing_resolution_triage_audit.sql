-- Audit the Android missing-resolution triage view.

-- 1. Bucket totals.
SELECT
  review_lane,
  COUNT(*) AS row_count
FROM v_android_missing_resolution_triage
GROUP BY review_lane
ORDER BY row_count DESC, review_lane;

-- 2. Recommended action totals.
SELECT
  recommended_action,
  COUNT(*) AS row_count
FROM v_android_missing_resolution_triage
GROUP BY recommended_action
ORDER BY row_count DESC, recommended_action;

-- 3. Top package clusters.
SELECT
  package_cluster_key,
  package_cluster_size,
  MIN(sample_id) AS first_sample_id,
  MAX(sample_id) AS last_sample_id
FROM v_android_missing_resolution_triage
GROUP BY package_cluster_key, package_cluster_size
ORDER BY package_cluster_size DESC, package_cluster_key;

-- 4. Detailed rows with VT tails first.
SELECT
  sample_id,
  sha256,
  platform,
  source_batch_label,
  android_package_name,
  package_cluster_key,
  package_cluster_size,
  package_cluster_rank,
  vt_family_token,
  vt_suggested_threat_label,
  review_lane,
  recommended_action,
  authority_gap_reason
FROM v_android_missing_resolution_triage
ORDER BY
  CASE WHEN review_lane = 'vt_tail_review' THEN 0 ELSE 1 END,
  package_cluster_size DESC,
  sample_id;
