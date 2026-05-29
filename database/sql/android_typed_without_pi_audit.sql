-- QA audit for typed Android authority rows that still lack Permission Intel observations.

-- 1. Overall count
SELECT
  COUNT(*) AS typed_rows_without_pi
FROM v_android_sample_family_type_authority a
WHERE a.authority_bucket = 'authority_family_typed'
  AND NOT EXISTS (
    SELECT 1
    FROM android_permission_intel.android_permission_obs_sample p
    WHERE p.sample_id = a.sample_id
  );

-- 2. By family / type
SELECT
  a.family_slug,
  a.type_slug,
  COUNT(*) AS rows_without_pi
FROM v_android_sample_family_type_authority a
WHERE a.authority_bucket = 'authority_family_typed'
  AND NOT EXISTS (
    SELECT 1
    FROM android_permission_intel.android_permission_obs_sample p
    WHERE p.sample_id = a.sample_id
  )
GROUP BY a.family_slug, a.type_slug
ORDER BY rows_without_pi DESC, a.family_slug
LIMIT 100;

-- 3. By submission year
SELECT
  COALESCE(YEAR(a.vt_first_submission_at_utc), 0) AS year_bucket,
  COUNT(*) AS rows_without_pi
FROM v_android_sample_family_type_authority a
WHERE a.authority_bucket = 'authority_family_typed'
  AND NOT EXISTS (
    SELECT 1
    FROM android_permission_intel.android_permission_obs_sample p
    WHERE p.sample_id = a.sample_id
  )
GROUP BY COALESCE(YEAR(a.vt_first_submission_at_utc), 0)
ORDER BY year_bucket;

-- 4. By analysis lane
SELECT
  COALESCE(c.analysis_lane, '<blank>') AS analysis_lane,
  COUNT(*) AS rows_without_pi
FROM v_android_sample_family_type_authority a
JOIN malware_sample_catalog c
  ON c.sample_id = a.sample_id
WHERE a.authority_bucket = 'authority_family_typed'
  AND NOT EXISTS (
    SELECT 1
    FROM android_permission_intel.android_permission_obs_sample p
    WHERE p.sample_id = a.sample_id
  )
GROUP BY COALESCE(c.analysis_lane, '<blank>')
ORDER BY rows_without_pi DESC, analysis_lane;

-- 5. Completeness profile for the no-PI rows
SELECT
  SUM(CASE WHEN COALESCE(c.android_package_name, '') = '' THEN 1 ELSE 0 END) AS blank_package_rows,
  SUM(CASE WHEN COALESCE(c.vt_family_token, '') = '' THEN 1 ELSE 0 END) AS blank_vt_family_rows,
  SUM(CASE WHEN COALESCE(c.vt_suggested_label, '') = '' THEN 1 ELSE 0 END) AS blank_vt_label_rows,
  SUM(CASE WHEN COALESCE(c.classification_primary, '') = '' THEN 1 ELSE 0 END) AS blank_primary_rows,
  SUM(CASE WHEN COALESCE(c.classification_subtype, '') = '' THEN 1 ELSE 0 END) AS blank_subtype_rows
FROM v_android_sample_family_type_authority a
JOIN malware_sample_catalog c
  ON c.sample_id = a.sample_id
WHERE a.authority_bucket = 'authority_family_typed'
  AND NOT EXISTS (
    SELECT 1
    FROM android_permission_intel.android_permission_obs_sample p
    WHERE p.sample_id = a.sample_id
  );

-- 6. Detailed sample queue
SELECT
  a.sample_id,
  a.family_slug,
  a.type_slug,
  c.analysis_lane,
  c.source_batch_label,
  c.android_package_name,
  c.classification_primary,
  c.classification_subtype,
  c.vt_family_token,
  c.vt_suggested_label,
  a.vt_first_submission_at_utc
FROM v_android_sample_family_type_authority a
JOIN malware_sample_catalog c
  ON c.sample_id = a.sample_id
WHERE a.authority_bucket = 'authority_family_typed'
  AND NOT EXISTS (
    SELECT 1
    FROM android_permission_intel.android_permission_obs_sample p
    WHERE p.sample_id = a.sample_id
  )
ORDER BY c.analysis_lane, a.family_slug, a.sample_id;
