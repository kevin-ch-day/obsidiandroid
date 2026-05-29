-- QA audit for false-positive suppression coverage.
-- Purpose:
--   * prove whether vt_false_positive_suppression_rule affects the current live review view
--   * provide a suppression-aware alternative audit surface without changing the live view

-- 1. Current live view count (suppression-unaware)
SELECT
  'live_view_total' AS metric,
  COUNT(*) AS row_count
FROM v_vt_false_positive_review_candidates;

-- 2. Suppression coverage inside the live view
WITH live_rows AS (
  SELECT
    v.sample_id,
    v.sample_label,
    v.android_package_name
  FROM v_vt_false_positive_review_candidates v
),
annotated AS (
  SELECT
    l.*,
    CASE
      WHEN EXISTS (
        SELECT 1
        FROM vt_false_positive_suppression_rule s
        WHERE s.active_flag = 1
          AND (
            (s.scope_type = 'sample' AND s.scope_value = CAST(l.sample_id AS CHAR))
            OR (s.scope_type = 'package' AND s.scope_value = l.android_package_name)
            OR (s.scope_type = 'label_pattern' AND s.scope_value = l.sample_label)
            OR (s.scope_type = 'family' AND LOWER(TRIM(s.scope_value)) = LOWER(TRIM(COALESCE(l.sample_label, ''))))
          )
      ) THEN 1
      ELSE 0
    END AS has_matching_suppression
  FROM live_rows l
)
SELECT
  has_matching_suppression,
  COUNT(*) AS row_count
FROM annotated
GROUP BY has_matching_suppression
ORDER BY has_matching_suppression DESC;

-- 3. Suppression-aware candidate count
WITH live_rows AS (
  SELECT
    v.*
  FROM v_vt_false_positive_review_candidates v
),
filtered AS (
  SELECT
    l.*
  FROM live_rows l
  WHERE NOT EXISTS (
    SELECT 1
    FROM vt_false_positive_suppression_rule s
    WHERE s.active_flag = 1
      AND (
        (s.scope_type = 'sample' AND s.scope_value = CAST(l.sample_id AS CHAR))
        OR (s.scope_type = 'package' AND s.scope_value = l.android_package_name)
        OR (s.scope_type = 'label_pattern' AND s.scope_value = l.sample_label)
        OR (s.scope_type = 'family' AND LOWER(TRIM(s.scope_value)) = LOWER(TRIM(COALESCE(l.sample_label, ''))))
      )
  )
)
SELECT
  'suppression_aware_total' AS metric,
  COUNT(*) AS row_count
FROM filtered;

-- 4. Top suppressed rows still present in the live view
WITH live_rows AS (
  SELECT
    v.sample_id,
    v.platform,
    v.sample_label,
    v.android_package_name,
    v.vt_malicious_count,
    v.raw_detection_ratio
  FROM v_vt_false_positive_review_candidates v
),
matched AS (
  SELECT
    l.*,
    s.rule_id,
    s.rule_name,
    s.scope_type,
    s.scope_value,
    s.suppression_weight,
    s.reason_code
  FROM live_rows l
  JOIN vt_false_positive_suppression_rule s
    ON s.active_flag = 1
   AND (
      (s.scope_type = 'sample' AND s.scope_value = CAST(l.sample_id AS CHAR))
      OR (s.scope_type = 'package' AND s.scope_value = l.android_package_name)
      OR (s.scope_type = 'label_pattern' AND s.scope_value = l.sample_label)
      OR (s.scope_type = 'family' AND LOWER(TRIM(s.scope_value)) = LOWER(TRIM(COALESCE(l.sample_label, ''))))
   )
)
SELECT
  sample_id,
  platform,
  COALESCE(NULLIF(sample_label, ''), '<blank>') AS sample_label,
  COALESCE(NULLIF(android_package_name, ''), '<blank>') AS android_package_name,
  vt_malicious_count,
  raw_detection_ratio,
  rule_id,
  rule_name,
  scope_type,
  scope_value,
  suppression_weight,
  reason_code
FROM matched
ORDER BY suppression_weight DESC, vt_malicious_count ASC, sample_id
LIMIT 100;
