-- Read-only audit + repair worklist for Android rows that have Permission Intel
-- observations but still lack `classification_primary`.
--
-- Scope:
--   - exact parity with readiness `missing_primary_labels`
--   - Android rows only (`platform = 'android'`)
--   - requires at least one Permission Intel observation
--   - focuses on rows where `classification_primary` is blank after trim
--
-- Run from the primary schema, for example:
--   mysql -t -D erebus_threat_intel_prod < database/sql/android_missing_primary_label_audit.sql
--
-- Notes:
--   - This is intentionally read-only.
--   - The authority view is joined as enrichment only, so rows without
--     authority coverage still appear in the gap count and worklist.
--   - The detailed worklist suggests which rows are safest to close by type
--     backfill versus which rows still require taxonomy or package review.

SET NAMES utf8mb4;

-- -----------------------------------------------------------------------------
-- Q1) Exact parity count for readiness `missing_primary_labels`
-- -----------------------------------------------------------------------------
WITH pi_samples AS (
    SELECT DISTINCT sample_id
    FROM android_permission_intel.android_permission_obs_sample
    WHERE sample_id IS NOT NULL
),
missing_primary AS (
    SELECT
        msc.sample_id
    FROM malware_sample_catalog AS msc
    JOIN pi_samples AS pi
      ON pi.sample_id = msc.sample_id
    WHERE LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
      AND COALESCE(TRIM(msc.classification_primary), '') = ''
)
SELECT COUNT(*) AS missing_primary_label_rows
FROM missing_primary;

-- -----------------------------------------------------------------------------
-- Q2) Summary by authority posture and recommended action
-- -----------------------------------------------------------------------------
WITH pi_samples AS (
    SELECT DISTINCT sample_id
    FROM android_permission_intel.android_permission_obs_sample
    WHERE sample_id IS NOT NULL
),
vt_confidence AS (
    SELECT
        sample_id,
        LOWER(TRIM(COALESCE(confidence_bucket, ''))) AS confidence_bucket
    FROM vt_sample_verdict_confidence_current
    WHERE sample_id IS NOT NULL
),
base AS (
    SELECT
        msc.sample_id,
        msc.platform,
        msc.analysis_lane,
        msc.source_batch_label,
        msc.android_package_name,
        msc.classification_primary,
        msc.classification_subtype,
        msc.vt_family_token,
        msc.vt_suggested_label,
        msc.vt_first_submission_at_utc,
        a.resolved_family_lc,
        a.family_slug,
        a.type_slug,
        a.authority_bucket,
        a.authority_gap_reason,
        a.raw_vs_authority_status,
        vc.confidence_bucket
    FROM malware_sample_catalog AS msc
    JOIN pi_samples AS pi
      ON pi.sample_id = msc.sample_id
    LEFT JOIN v_android_sample_family_type_authority AS a
      ON a.sample_id = msc.sample_id
    LEFT JOIN vt_confidence AS vc
      ON vc.sample_id = msc.sample_id
    WHERE LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
      AND COALESCE(TRIM(msc.classification_primary), '') = ''
)
SELECT
    COALESCE(authority_bucket, '<no_authority_row>') AS authority_bucket,
    COALESCE(authority_gap_reason, '<null>') AS authority_gap_reason,
    COALESCE(raw_vs_authority_status, '<null>') AS raw_vs_authority_status,
    CASE
        WHEN authority_bucket = 'authority_family_typed'
             AND COALESCE(TRIM(type_slug), '') <> '' THEN 'backfill_primary_from_authority_type'
        WHEN authority_bucket = 'authority_family_unknown_type' THEN 'review_unknown_authority_type'
        WHEN authority_bucket = 'missing_resolved_family' THEN 'route_to_missing_resolution_queue'
        WHEN authority_bucket = 'resolved_but_no_authority_family' THEN 'review_family_authority_before_backfill'
        WHEN authority_bucket = 'generic_label_candidate' THEN 'policy_hold_or_generic_review'
        WHEN authority_bucket = 'resolved_unknown' THEN 'review_unknown_family_resolution'
        WHEN COALESCE(TRIM(classification_subtype), '') <> '' THEN 'review_subtype_without_primary'
        ELSE 'review_catalog_label_gap'
    END AS recommended_action,
    COUNT(*) AS sample_rows,
    SUM(CASE WHEN confidence_bucket IN ('high', 'strong') THEN 1 ELSE 0 END) AS high_or_strong_vt_rows
FROM base
GROUP BY
    COALESCE(authority_bucket, '<no_authority_row>'),
    COALESCE(authority_gap_reason, '<null>'),
    COALESCE(raw_vs_authority_status, '<null>'),
    recommended_action
ORDER BY sample_rows DESC, authority_bucket, authority_gap_reason, recommended_action;

-- -----------------------------------------------------------------------------
-- Q3) Family / type / subtype breakdown
-- -----------------------------------------------------------------------------
WITH pi_samples AS (
    SELECT DISTINCT sample_id
    FROM android_permission_intel.android_permission_obs_sample
    WHERE sample_id IS NOT NULL
)
SELECT
    COALESCE(a.family_slug, '<no_authority_family>') AS family_slug,
    COALESCE(a.type_slug, '<no_authority_type>') AS type_slug,
    COALESCE(NULLIF(TRIM(msc.classification_subtype), ''), '<blank>') AS raw_classification_subtype,
    COUNT(*) AS sample_rows
FROM malware_sample_catalog AS msc
JOIN pi_samples AS pi
  ON pi.sample_id = msc.sample_id
LEFT JOIN v_android_sample_family_type_authority AS a
  ON a.sample_id = msc.sample_id
WHERE LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
  AND COALESCE(TRIM(msc.classification_primary), '') = ''
GROUP BY family_slug, type_slug, raw_classification_subtype
ORDER BY sample_rows DESC, family_slug, type_slug, raw_classification_subtype
LIMIT 150;

-- -----------------------------------------------------------------------------
-- Q4) Batch / package cluster / VT hint breakdown
-- -----------------------------------------------------------------------------
WITH pi_samples AS (
    SELECT DISTINCT sample_id
    FROM android_permission_intel.android_permission_obs_sample
    WHERE sample_id IS NOT NULL
),
base AS (
    SELECT
        msc.sample_id,
        COALESCE(NULLIF(TRIM(msc.source_batch_label), ''), '<blank>') AS source_batch_label,
        COALESCE(NULLIF(TRIM(msc.analysis_lane), ''), '<blank>') AS analysis_lane,
        COALESCE(NULLIF(TRIM(msc.android_package_name), ''), '<blank>') AS android_package_name,
        COALESCE(NULLIF(TRIM(msc.vt_family_token), ''), '<blank>') AS vt_family_token,
        COALESCE(NULLIF(TRIM(msc.vt_suggested_label), ''), '<blank>') AS vt_suggested_label,
        CASE
            WHEN msc.android_package_name IS NULL OR TRIM(msc.android_package_name) = '' THEN '<blank>'
            WHEN msc.android_package_name LIKE '%.%' THEN SUBSTRING_INDEX(msc.android_package_name, '.', 2)
            ELSE msc.android_package_name
        END AS package_cluster_key
    FROM malware_sample_catalog AS msc
    JOIN pi_samples AS pi
      ON pi.sample_id = msc.sample_id
    WHERE LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
      AND COALESCE(TRIM(msc.classification_primary), '') = ''
)
SELECT
    source_batch_label,
    analysis_lane,
    package_cluster_key,
    vt_family_token,
    vt_suggested_label,
    COUNT(*) AS sample_rows
FROM base
GROUP BY source_batch_label, analysis_lane, package_cluster_key, vt_family_token, vt_suggested_label
ORDER BY sample_rows DESC, source_batch_label, analysis_lane, package_cluster_key
LIMIT 150;

-- -----------------------------------------------------------------------------
-- Q5) Safe-close candidates versus unresolved review debt
-- -----------------------------------------------------------------------------
WITH pi_samples AS (
    SELECT DISTINCT sample_id
    FROM android_permission_intel.android_permission_obs_sample
    WHERE sample_id IS NOT NULL
),
vt_confidence AS (
    SELECT
        sample_id,
        LOWER(TRIM(COALESCE(confidence_bucket, ''))) AS confidence_bucket
    FROM vt_sample_verdict_confidence_current
    WHERE sample_id IS NOT NULL
),
base AS (
    SELECT
        msc.sample_id,
        msc.classification_subtype,
        a.type_slug,
        a.authority_bucket,
        a.authority_gap_reason,
        vc.confidence_bucket
    FROM malware_sample_catalog AS msc
    JOIN pi_samples AS pi
      ON pi.sample_id = msc.sample_id
    LEFT JOIN v_android_sample_family_type_authority AS a
      ON a.sample_id = msc.sample_id
    LEFT JOIN vt_confidence AS vc
      ON vc.sample_id = msc.sample_id
    WHERE LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
      AND COALESCE(TRIM(msc.classification_primary), '') = ''
)
SELECT
    CASE
        WHEN authority_bucket = 'authority_family_typed'
             AND COALESCE(TRIM(type_slug), '') <> '' THEN 'safe_authority_type_backfill'
        WHEN authority_bucket = 'authority_family_unknown_type' THEN 'needs_type_taxonomy_repair'
        WHEN authority_bucket = 'missing_resolved_family' THEN 'needs_missing_resolution_triage'
        WHEN authority_bucket = 'resolved_but_no_authority_family' THEN 'needs_family_authority_curation'
        WHEN authority_bucket = 'generic_label_candidate' THEN 'needs_policy_or_generic_token_review'
        WHEN authority_bucket = 'resolved_unknown' THEN 'needs_unknown_resolution_review'
        WHEN COALESCE(TRIM(classification_subtype), '') <> '' THEN 'subtype_present_but_primary_missing'
        ELSE 'uncategorized_catalog_gap'
    END AS close_strategy,
    COUNT(*) AS sample_rows,
    SUM(CASE WHEN confidence_bucket IN ('high', 'strong') THEN 1 ELSE 0 END) AS high_or_strong_vt_rows
FROM base
GROUP BY close_strategy
ORDER BY sample_rows DESC, close_strategy;

-- -----------------------------------------------------------------------------
-- Q6) Detailed repair worklist
-- -----------------------------------------------------------------------------
WITH pi_obs AS (
    SELECT
        sample_id,
        COUNT(*) AS pi_observation_count
    FROM android_permission_intel.android_permission_obs_sample
    WHERE sample_id IS NOT NULL
    GROUP BY sample_id
),
vt_confidence AS (
    SELECT
        sample_id,
        LOWER(TRIM(COALESCE(confidence_bucket, ''))) AS confidence_bucket
    FROM vt_sample_verdict_confidence_current
    WHERE sample_id IS NOT NULL
),
base AS (
    SELECT
        msc.sample_id,
        msc.sha256,
        msc.platform,
        msc.file_extension,
        msc.analysis_lane,
        COALESCE(NULLIF(TRIM(msc.source_batch_label), ''), '<blank>') AS source_batch_label,
        COALESCE(NULLIF(TRIM(msc.android_package_name), ''), '<blank>') AS android_package_name,
        msc.vt_first_submission_at_utc,
        msc.vt_first_seen_itw_date,
        COALESCE(msc.vt_first_seen_itw_date, msc.vt_first_submission_at_utc) AS effective_first_seen_at_utc,
        COALESCE(NULLIF(TRIM(msc.classification_primary), ''), '<blank>') AS raw_classification_primary,
        COALESCE(NULLIF(TRIM(msc.classification_subtype), ''), '<blank>') AS raw_classification_subtype,
        COALESCE(NULLIF(TRIM(msc.vt_family_token), ''), '<blank>') AS vt_family_token,
        COALESCE(NULLIF(TRIM(msc.vt_suggested_label), ''), '<blank>') AS vt_suggested_label,
        a.resolved_family_lc,
        a.family_slug,
        a.type_slug,
        a.authority_bucket,
        a.authority_gap_reason,
        a.raw_vs_authority_status,
        vc.confidence_bucket,
        pi.pi_observation_count,
        CASE
            WHEN msc.android_package_name IS NULL OR TRIM(msc.android_package_name) = '' THEN '<blank>'
            WHEN msc.android_package_name LIKE '%.%' THEN SUBSTRING_INDEX(msc.android_package_name, '.', 2)
            ELSE msc.android_package_name
        END AS package_cluster_key
    FROM malware_sample_catalog AS msc
    JOIN pi_obs AS pi
      ON pi.sample_id = msc.sample_id
    LEFT JOIN v_android_sample_family_type_authority AS a
      ON a.sample_id = msc.sample_id
    LEFT JOIN vt_confidence AS vc
      ON vc.sample_id = msc.sample_id
    WHERE LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
      AND COALESCE(TRIM(msc.classification_primary), '') = ''
),
scored AS (
    SELECT
        b.*,
        COUNT(*) OVER (PARTITION BY b.package_cluster_key) AS package_cluster_size
    FROM base AS b
)
SELECT
    sample_id,
    sha256,
    platform,
    file_extension,
    analysis_lane,
    source_batch_label,
    android_package_name,
    package_cluster_key,
    package_cluster_size,
    vt_first_submission_at_utc,
    vt_first_seen_itw_date,
    effective_first_seen_at_utc,
    raw_classification_primary,
    raw_classification_subtype,
    vt_family_token,
    vt_suggested_label,
    COALESCE(NULLIF(TRIM(resolved_family_lc), ''), '<blank>') AS resolved_family_lc,
    COALESCE(NULLIF(TRIM(family_slug), ''), '<blank>') AS family_slug,
    COALESCE(NULLIF(TRIM(type_slug), ''), '<blank>') AS type_slug,
    COALESCE(NULLIF(TRIM(authority_bucket), ''), '<no_authority_row>') AS authority_bucket,
    COALESCE(NULLIF(TRIM(authority_gap_reason), ''), '<null>') AS authority_gap_reason,
    COALESCE(NULLIF(TRIM(raw_vs_authority_status), ''), '<null>') AS raw_vs_authority_status,
    COALESCE(NULLIF(TRIM(confidence_bucket), ''), '<unavailable>') AS vt_confidence_bucket,
    pi_observation_count,
    CASE
        WHEN authority_bucket = 'authority_family_typed'
             AND COALESCE(TRIM(type_slug), '') <> '' THEN 'backfill_primary_from_authority_type'
        WHEN authority_bucket = 'authority_family_unknown_type' THEN 'review_unknown_authority_type'
        WHEN authority_bucket = 'missing_resolved_family' THEN 'route_to_missing_resolution_queue'
        WHEN authority_bucket = 'resolved_but_no_authority_family' THEN 'review_family_authority_before_backfill'
        WHEN authority_bucket = 'generic_label_candidate' THEN 'policy_hold_or_generic_review'
        WHEN authority_bucket = 'resolved_unknown' THEN 'review_unknown_family_resolution'
        WHEN package_cluster_key = '<blank>' THEN 'review_blank_package_gap'
        WHEN raw_classification_subtype <> '<blank>' THEN 'review_subtype_without_primary'
        ELSE 'review_catalog_label_gap'
    END AS recommended_action,
    CASE
        WHEN authority_bucket = 'authority_family_typed'
             AND COALESCE(TRIM(type_slug), '') <> ''
             AND COALESCE(TRIM(raw_classification_subtype), '') <> '' THEN 'high'
        WHEN authority_bucket = 'authority_family_typed'
             AND COALESCE(TRIM(type_slug), '') <> '' THEN 'medium'
        WHEN authority_bucket IN ('missing_resolved_family', 'resolved_but_no_authority_family') THEN 'high'
        WHEN authority_bucket IN ('authority_family_unknown_type', 'generic_label_candidate', 'resolved_unknown') THEN 'medium'
        ELSE 'low'
    END AS repair_priority
FROM scored
ORDER BY
    (authority_bucket = 'authority_family_typed'
        AND COALESCE(TRIM(type_slug), '') <> '') DESC,
    (COALESCE(confidence_bucket, '') IN ('high', 'strong')) DESC,
    (package_cluster_size > 1) DESC,
    effective_first_seen_at_utc DESC,
    sample_id DESC;
