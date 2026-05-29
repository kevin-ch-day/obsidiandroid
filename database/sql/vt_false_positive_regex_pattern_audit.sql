USE erebus_threat_intel_prod;

-- Regex-pattern audit for repeated false-positive review shapes.
-- Goal:
--   * surface structural label patterns rather than one-off names
--   * separate legitimate installer/admin-tool churn from generic or suspicious labels

-- 1. False-positive review candidates grouped by regex bucket
WITH fp AS (
  SELECT
    sample_id,
    platform,
    COALESCE(sample_label, '') AS sample_label,
    COALESCE(android_package_name, '') AS android_package_name,
    vt_malicious_count,
    raw_detection_ratio
  FROM v_vt_false_positive_review_candidates
),
buckets AS (
  SELECT
    sample_id,
    platform,
    sample_label,
    android_package_name,
    vt_malicious_count,
    raw_detection_ratio,
    CASE
      WHEN LOWER(sample_label) REGEXP '(^|[^a-z])(install|installer|setup|updater|update|launcher|assistant|remoteassist|pageant)([^a-z]|$)'
        THEN 'installer_or_admin_tool'
      WHEN LOWER(sample_label) REGEXP '(^|[^a-z])(uninstall)([^a-z]|$)'
        THEN 'uninstall_utility'
      WHEN LOWER(sample_label) REGEXP '\\.(exe|dll|zip|jar|doc|png)$'
        THEN 'filename_extension'
      WHEN LOWER(sample_label) REGEXP '^[a-z0-9._+-]+$' AND sample_label LIKE '%.%'
        THEN 'package_or_hash_like'
      WHEN LOWER(sample_label) REGEXP 'phishing|unknown|unclassified|banker trojan'
        THEN 'generic_detection_name'
      ELSE 'other'
    END AS regex_bucket
  FROM fp
)
SELECT
  regex_bucket,
  platform,
  COUNT(*) AS rows_total,
  ROUND(AVG(vt_malicious_count), 2) AS avg_malicious,
  ROUND(AVG(raw_detection_ratio), 4) AS avg_ratio,
  GROUP_CONCAT(DISTINCT sample_label ORDER BY sample_label SEPARATOR ' | ') AS labels
FROM buckets
GROUP BY regex_bucket, platform
ORDER BY rows_total DESC, regex_bucket, platform;

-- 2. Exact installer/admin-tool labels worth suppression review
SELECT
  sample_label,
  platform,
  COUNT(*) AS row_count,
  MIN(vt_malicious_count) AS min_malicious,
  MAX(vt_malicious_count) AS max_malicious,
  ROUND(AVG(vt_malicious_count), 2) AS avg_malicious,
  GROUP_CONCAT(sample_id ORDER BY sample_id) AS sample_ids
FROM v_vt_false_positive_review_candidates
WHERE LOWER(sample_label) REGEXP '(^|[^a-z])(install|installer|setup|updater|update|launcher|assistant|remoteassist|pageant)([^a-z]|$)'
GROUP BY sample_label, platform
ORDER BY row_count DESC, avg_malicious, sample_label;

-- 3. Generic/placeholder review labels that should usually stay out of authority work
SELECT
  sample_label,
  platform,
  COUNT(*) AS row_count,
  GROUP_CONCAT(sample_id ORDER BY sample_id) AS sample_ids
FROM v_vt_false_positive_review_candidates
WHERE LOWER(sample_label) REGEXP 'phishing|unknown|unclassified|banker trojan'
GROUP BY sample_label, platform
ORDER BY row_count DESC, sample_label;

-- 4. Android missing-resolution rows grouped by structural package/VT-label shape
WITH miss AS (
  SELECT
    c.sample_id,
    COALESCE(c.android_package_name, '') AS pkg,
    COALESCE(c.vt_suggested_label, '') AS vt_label,
    COALESCE(c.vt_family_token, '') AS vt_token,
    COALESCE(c.classification_primary, '') AS p1,
    COALESCE(c.classification_subtype, '') AS p2
  FROM malware_sample_catalog c
  JOIN v_android_sample_family_type_authority a
    ON a.sample_id = c.sample_id
  WHERE a.authority_bucket IN ('missing_resolved_family', 'resolved_but_no_authority_family')
)
SELECT
  CASE
    WHEN LOWER(pkg) REGEXP '^[a-z0-9]+(\\.[a-z0-9_]+){2,}$'
      THEN 'package_like'
    WHEN LOWER(vt_label) REGEXP '^trojan\\.[a-z0-9_+-]+/[a-z0-9_+-]+$'
      THEN 'two_part_vt_label'
    WHEN LOWER(vt_label) REGEXP '^ransomware\\.[a-z0-9_+-]+/[a-z0-9_+-]+$'
      THEN 'two_part_ransomware_label'
    WHEN LOWER(vt_token) REGEXP 'jiagu|boogr|genericfca|fakeapp|bankbot|spyagent'
      THEN 'generic_vt_tail_token'
    WHEN LOWER(CONCAT_WS(' ', p1, p2)) REGEXP 'banker|spyware|locker|worm|dropper'
      THEN 'coarse_type_only'
    ELSE 'other'
  END AS pattern_bucket,
  COUNT(*) AS rows_total,
  GROUP_CONCAT(sample_id ORDER BY sample_id) AS sample_ids
FROM miss
GROUP BY pattern_bucket
ORDER BY rows_total DESC, pattern_bucket;
