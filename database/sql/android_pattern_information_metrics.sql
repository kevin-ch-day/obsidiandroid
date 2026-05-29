-- Information-theoretic and concentration audit for residual Android repair queues.
-- Purpose:
--   * quantify whether remaining debt is concentrated or diffuse
--   * distinguish token-driven debt from package-cluster debt
--   * score VT tail tokens by purity vs noise

-- 1. Residual unresolved-family token distribution math
WITH unresolved AS (
  SELECT LOWER(TRIM(a.resolved_family_lc)) COLLATE utf8mb4_general_ci AS token
  FROM v_android_sample_family_type_authority a
  WHERE a.authority_bucket = 'resolved_but_no_authority_family'
),
counts AS (
  SELECT token, COUNT(*) AS n
  FROM unresolved
  GROUP BY token
),
total AS (
  SELECT SUM(n) AS total_n, COUNT(*) AS k
  FROM counts
)
SELECT
  'resolved_but_no_authority_family' AS surface_name,
  total_n,
  k AS distinct_items,
  ROUND(SUM(-(n / total_n) * LOG(n / total_n) / LOG(2)), 4) AS entropy_bits,
  ROUND(SUM(-(n / total_n) * LOG(n / total_n) / LOG(2)) / (LOG(k) / LOG(2)), 4) AS normalized_entropy,
  ROUND(SUM(POW(n / total_n, 2)), 4) AS hhi
FROM counts
CROSS JOIN total;

-- 2. Missing-resolution package distribution math
WITH miss AS (
  SELECT COALESCE(NULLIF(c.android_package_name, ''), '<blank>') AS pkg
  FROM malware_sample_catalog c
  JOIN v_android_sample_family_type_authority a
    ON a.sample_id = c.sample_id
  WHERE a.authority_bucket = 'missing_resolved_family'
),
counts AS (
  SELECT pkg, COUNT(*) AS n
  FROM miss
  GROUP BY pkg
),
total AS (
  SELECT SUM(n) AS total_n, COUNT(*) AS k
  FROM counts
)
SELECT
  'missing_resolved_family_package_clusters' AS surface_name,
  total_n,
  k AS distinct_items,
  ROUND(SUM(-(n / total_n) * LOG(n / total_n) / LOG(2)), 4) AS entropy_bits,
  ROUND(SUM(-(n / total_n) * LOG(n / total_n) / LOG(2)) / (LOG(k) / LOG(2)), 4) AS normalized_entropy,
  ROUND(SUM(POW(n / total_n, 2)), 4) AS hhi
FROM counts
CROSS JOIN total;

-- 3. Package-cluster lift vs Android catalog base rates
WITH pkg_base AS (
  SELECT
    COALESCE(NULLIF(android_package_name, ''), '<blank>') AS pkg,
    COUNT(*) AS base_n
  FROM malware_sample_catalog
  WHERE platform = 'android' AND file_extension = 'apk'
  GROUP BY COALESCE(NULLIF(android_package_name, ''), '<blank>')
),
miss AS (
  SELECT
    COALESCE(NULLIF(c.android_package_name, ''), '<blank>') AS pkg,
    COUNT(*) AS miss_n
  FROM malware_sample_catalog c
  JOIN v_android_sample_family_type_authority a
    ON a.sample_id = c.sample_id
  WHERE a.authority_bucket = 'missing_resolved_family'
  GROUP BY COALESCE(NULLIF(c.android_package_name, ''), '<blank>')
),
totals AS (
  SELECT
    (SELECT COUNT(*) FROM malware_sample_catalog WHERE platform = 'android' AND file_extension = 'apk') AS base_total,
    (SELECT COUNT(*) FROM v_android_sample_family_type_authority WHERE authority_bucket = 'missing_resolved_family') AS miss_total
)
SELECT
  m.pkg,
  m.miss_n,
  b.base_n,
  ROUND(m.miss_n / miss_total, 4) AS miss_share,
  ROUND(b.base_n / base_total, 4) AS base_share,
  ROUND((m.miss_n / miss_total) / NULLIF((b.base_n / base_total), 0), 2) AS raw_lift,
  ROUND(((m.miss_n / miss_total) / NULLIF((b.base_n / base_total), 0)) * LOG(1 + m.miss_n), 2) AS support_weighted_lift
FROM miss m
JOIN pkg_base b
  ON b.pkg = m.pkg
CROSS JOIN totals
ORDER BY support_weighted_lift DESC, m.miss_n DESC, m.pkg;

-- 4. VT family-tail purity metrics for noisy/important tails
WITH tails AS (
  SELECT
    LOWER(TRIM(COALESCE(vt_family_token, ''))) AS vt_token,
    LOWER(TRIM(COALESCE(family_label, ''))) AS family_label
  FROM malware_sample_catalog
  WHERE platform = 'android'
    AND file_extension = 'apk'
    AND COALESCE(vt_family_token, '') <> ''
),
counts AS (
  SELECT
    vt_token,
    COALESCE(NULLIF(family_label, ''), '<blank>') AS family_label,
    COUNT(*) AS n
  FROM tails
  GROUP BY vt_token, COALESCE(NULLIF(family_label, ''), '<blank>')
),
totals AS (
  SELECT
    vt_token,
    SUM(n) AS total_n,
    COUNT(*) AS distinct_labels,
    MAX(n) AS top_n
  FROM counts
  GROUP BY vt_token
)
SELECT
  t.vt_token,
  t.total_n,
  t.distinct_labels,
  ROUND(t.top_n / t.total_n, 4) AS top_label_purity,
  ROUND(SUM(-(c.n / t.total_n) * LOG(c.n / t.total_n) / LOG(2)), 4) AS entropy_bits,
  GROUP_CONCAT(CONCAT(c.family_label, ':', c.n) ORDER BY c.n DESC SEPARATOR ' | ') AS label_mix
FROM totals t
JOIN counts c
  ON c.vt_token = t.vt_token
WHERE t.vt_token IN ('boogr', 'jiagu', 'fklz', 'genericfca', 'spybanker')
GROUP BY t.vt_token, t.total_n, t.distinct_labels, t.top_n
ORDER BY t.total_n DESC, t.vt_token;

-- 5. Regex buckets over the false-positive review surface
WITH fp AS (
  SELECT
    sample_id,
    platform,
    COALESCE(sample_label, '') AS sample_label,
    vt_malicious_count,
    raw_detection_ratio
  FROM v_vt_false_positive_review_candidates
),
buckets AS (
  SELECT
    sample_id,
    platform,
    sample_label,
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
