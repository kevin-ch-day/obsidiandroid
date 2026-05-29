-- Live triage view for the unresolved Android/APK authority backlog.
--
-- Purpose:
--   * expose the concentrated package/provenance backlog as an operator queue
--   * keep already-suppressed provenance / low-context rows out of active repair
--   * keep low-context backlog rows out of family-authority curation
--   * surface the tiny VT-tail residue without treating it as family truth

CREATE OR REPLACE VIEW v_android_missing_resolution_triage AS
WITH suppression AS (
  SELECT
    msc.sample_id,
    MAX(s.suppression_weight) AS max_suppression_weight
  FROM malware_sample_catalog AS msc
  JOIN vt_false_positive_suppression_rule AS s
    ON s.active_flag = 1
   AND (s.starts_at_utc IS NULL OR s.starts_at_utc <= UTC_TIMESTAMP())
   AND (s.expires_at_utc IS NULL OR s.expires_at_utc > UTC_TIMESTAMP())
   AND (
      (s.scope_type = 'sample' AND s.scope_value = CAST(msc.sample_id AS CHAR))
      OR (s.scope_type = 'package' AND s.scope_value = msc.android_package_name)
   )
  GROUP BY msc.sample_id
),
base AS (
  SELECT
    msc.sample_id,
    msc.sha256,
    msc.platform,
    msc.file_extension,
    msc.analysis_lane,
    COALESCE(NULLIF(msc.source_batch_label, ''), '<blank>') AS source_batch_label,
    COALESCE(NULLIF(msc.android_package_name, ''), '<blank>') AS android_package_name,
    msc.vt_first_submission_at_utc,
    msc.vt_first_seen_itw_date,
    COALESCE(msc.vt_first_seen_itw_date, msc.vt_first_submission_at_utc) AS effective_first_seen_at_utc,
    a.family_raw,
    a.family_lc,
    a.resolved_family_lc,
    a.raw_classification_primary,
    a.raw_classification_subtype,
    COALESCE(NULLIF(msc.vt_family_token, ''), '<blank>') AS vt_family_token,
    COALESCE(NULLIF(msc.vt_suggested_label, ''), '<blank>') AS vt_suggested_threat_label,
    a.authority_bucket,
    a.authority_gap_reason,
    a.raw_vs_authority_status,
    CASE
      WHEN msc.android_package_name IS NULL OR TRIM(msc.android_package_name) = '' THEN '<blank>'
      WHEN msc.android_package_name LIKE '%.%' THEN SUBSTRING_INDEX(msc.android_package_name, '.', 2)
      ELSE msc.android_package_name
    END AS package_cluster_key
  FROM malware_sample_catalog msc
  JOIN v_android_sample_family_type_authority a
    ON a.sample_id = msc.sample_id
  LEFT JOIN suppression AS s
    ON s.sample_id = msc.sample_id
  WHERE a.authority_bucket = 'missing_resolved_family'
    AND COALESCE(s.max_suppression_weight, 0) <= 0
),
scored AS (
  SELECT
    b.*,
    COUNT(*) OVER (PARTITION BY b.package_cluster_key) AS package_cluster_size,
    ROW_NUMBER() OVER (
      PARTITION BY b.package_cluster_key
      ORDER BY b.effective_first_seen_at_utc ASC, b.sample_id ASC
    ) AS package_cluster_rank
  FROM base b
)
SELECT
  sample_id,
  sha256,
  platform,
  file_extension,
  analysis_lane,
  source_batch_label,
  android_package_name,
  vt_first_submission_at_utc,
  vt_first_seen_itw_date,
  effective_first_seen_at_utc,
  family_raw,
  family_lc,
  resolved_family_lc,
  raw_classification_primary,
  raw_classification_subtype,
  vt_family_token,
  vt_suggested_threat_label,
  authority_bucket,
  authority_gap_reason,
  raw_vs_authority_status,
  package_cluster_key,
  package_cluster_size,
  package_cluster_rank,
  CASE
    WHEN android_package_name = '<blank>' THEN 'blank_package_review'
    WHEN vt_family_token <> '<blank>' OR vt_suggested_threat_label <> '<blank>' THEN 'vt_tail_review'
    WHEN package_cluster_size > 1 THEN 'package_cluster_review'
    ELSE 'singleton_package_review'
  END AS review_lane,
  CASE
    WHEN android_package_name = '<blank>' THEN 'inspect_unknown_sparse'
    WHEN LOWER(vt_family_token) = 'jiagu' THEN 'policy_hold_packer'
    WHEN LOWER(vt_family_token) IN ('fklz', 'boogr')
      OR LOWER(vt_suggested_threat_label) LIKE '%boogr%' THEN 'policy_hold_generic'
    WHEN vt_family_token <> '<blank>' OR vt_suggested_threat_label <> '<blank>' THEN 'review_vt_tail'
    WHEN package_cluster_size > 1 THEN 'inspect_repeated_package_cluster'
    ELSE 'inspect_singleton_package'
  END AS recommended_action
FROM scored;
