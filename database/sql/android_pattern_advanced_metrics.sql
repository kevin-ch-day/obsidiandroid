-- Advanced information-theoretic / concentration audit for the residual
-- Android authority and FP review surfaces.

-- 1. Residual unresolved-family token tail:
-- entropy, normalized entropy, HHI, Theil, and Pareto mass share.
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
ranked AS (
  SELECT
    token,
    n,
    ROW_NUMBER() OVER (ORDER BY n DESC, token) AS rn
  FROM counts
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
  ROUND(SUM(-(n / total_n) * LOG(n / total_n) / LOG(2)) / NULLIF((LOG(k) / LOG(2)), 0), 4) AS normalized_entropy,
  ROUND(SUM(POW(n / total_n, 2)), 4) AS hhi,
  ROUND(SUM((n / total_n) * LOG((n / total_n) * k) / LOG(2)), 4) AS theil_t_bits,
  ROUND(SUM(CASE WHEN rn <= 1 THEN n ELSE 0 END) / total_n, 4) AS top1_share,
  ROUND(SUM(CASE WHEN rn <= 3 THEN n ELSE 0 END) / total_n, 4) AS top3_share,
  ROUND(SUM(CASE WHEN rn <= 5 THEN n ELSE 0 END) / total_n, 4) AS top5_share
FROM ranked
CROSS JOIN total;

-- 2. Missing-resolution package-cluster lane:
-- same concentration metrics.
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
ranked AS (
  SELECT
    pkg,
    n,
    ROW_NUMBER() OVER (ORDER BY n DESC, pkg) AS rn
  FROM counts
),
total AS (
  SELECT SUM(n) AS total_n, COUNT(*) AS k
  FROM counts
)
SELECT
  'missing_resolved_family_packages' AS surface_name,
  total_n,
  k AS distinct_items,
  ROUND(SUM(-(n / total_n) * LOG(n / total_n) / LOG(2)), 4) AS entropy_bits,
  ROUND(SUM(-(n / total_n) * LOG(n / total_n) / LOG(2)) / NULLIF((LOG(k) / LOG(2)), 0), 4) AS normalized_entropy,
  ROUND(SUM(POW(n / total_n, 2)), 4) AS hhi,
  ROUND(SUM((n / total_n) * LOG((n / total_n) * k) / LOG(2)), 4) AS theil_t_bits,
  ROUND(SUM(CASE WHEN rn <= 1 THEN n ELSE 0 END) / total_n, 4) AS top1_share,
  ROUND(SUM(CASE WHEN rn <= 3 THEN n ELSE 0 END) / total_n, 4) AS top3_share,
  ROUND(SUM(CASE WHEN rn <= 5 THEN n ELSE 0 END) / total_n, 4) AS top5_share
FROM ranked
CROSS JOIN total;

-- 3. Jensen-Shannon divergence between Android package base rates and the
-- missing-resolution package distribution.
WITH pkg_base AS (
  SELECT
    COALESCE(NULLIF(android_package_name, ''), '<blank>') AS pkg,
    COUNT(*) AS base_n
  FROM malware_sample_catalog
  WHERE platform = 'android' AND file_extension = 'apk'
  GROUP BY COALESCE(NULLIF(android_package_name, ''), '<blank>')
),
pkg_miss AS (
  SELECT
    COALESCE(NULLIF(c.android_package_name, ''), '<blank>') AS pkg,
    COUNT(*) AS miss_n
  FROM malware_sample_catalog c
  JOIN v_android_sample_family_type_authority a
    ON a.sample_id = c.sample_id
  WHERE a.authority_bucket = 'missing_resolved_family'
  GROUP BY COALESCE(NULLIF(c.android_package_name, ''), '<blank>')
),
support AS (
  SELECT
    COALESCE(b.pkg, m.pkg) AS pkg,
    COALESCE(base_n, 0) AS base_n,
    COALESCE(miss_n, 0) AS miss_n
  FROM pkg_base b
  LEFT JOIN pkg_miss m
    ON m.pkg = b.pkg
  UNION
  SELECT
    m.pkg,
    0 AS base_n,
    m.miss_n
  FROM pkg_miss m
  LEFT JOIN pkg_base b
    ON b.pkg = m.pkg
  WHERE b.pkg IS NULL
),
totals AS (
  SELECT
    SUM(base_n) AS base_total,
    SUM(miss_n) AS miss_total
  FROM support
)
SELECT
  'android_pkg_base_vs_missing_jsd' AS metric_name,
  ROUND(
    0.5 * SUM(
      CASE
        WHEN (base_n / base_total) > 0 THEN
          (base_n / base_total) * (
            LOG((base_n / base_total) / (((base_n / base_total) + (miss_n / miss_total)) / 2)) / LOG(2)
          )
        ELSE 0
      END
    )
    +
    0.5 * SUM(
      CASE
        WHEN (miss_n / miss_total) > 0 THEN
          (miss_n / miss_total) * (
            LOG((miss_n / miss_total) / (((base_n / base_total) + (miss_n / miss_total)) / 2)) / LOG(2)
          )
        ELSE 0
      END
    ),
    4
  ) AS js_divergence_bits
FROM support
CROSS JOIN totals;

-- 4. Mutual information between authority bucket and package blankness for
-- Android/APK rows. High MI means missing package data is strongly coupled
-- to the authority outcome.
WITH base AS (
  SELECT
    a.authority_bucket,
    CASE
      WHEN c.android_package_name IS NULL OR TRIM(c.android_package_name) = '' THEN 'blank_pkg'
      ELSE 'nonblank_pkg'
    END AS pkg_flag
  FROM v_android_sample_family_type_authority a
  JOIN malware_sample_catalog c
    ON c.sample_id = a.sample_id
  WHERE c.platform = 'android' AND c.file_extension = 'apk'
),
joint_counts AS (
  SELECT authority_bucket, pkg_flag, COUNT(*) AS n_xy
  FROM base
  GROUP BY authority_bucket, pkg_flag
),
x_counts AS (
  SELECT authority_bucket, SUM(n_xy) AS n_x
  FROM joint_counts
  GROUP BY authority_bucket
),
y_counts AS (
  SELECT pkg_flag, SUM(n_xy) AS n_y
  FROM joint_counts
  GROUP BY pkg_flag
),
totals AS (
  SELECT SUM(n_xy) AS n_total
  FROM joint_counts
)
SELECT
  'authority_bucket_vs_package_blankness_mi' AS metric_name,
  ROUND(SUM(
    (n_xy / n_total) * LOG((n_xy * n_total) / (n_x * n_y)) / LOG(2)
  ), 4) AS mutual_information_bits
FROM joint_counts j
JOIN x_counts x
  ON x.authority_bucket = j.authority_bucket
JOIN y_counts y
  ON y.pkg_flag = j.pkg_flag
CROSS JOIN totals;

-- 5. Mutual information between effective FP review platform and regex bucket.
WITH fp AS (
  SELECT
    sample_id,
    platform,
    COALESCE(sample_label, '') AS sample_label
  FROM v_vt_false_positive_review_candidates_effective
),
bucketed AS (
  SELECT
    platform,
    CASE
      WHEN LOWER(sample_label) REGEXP '(^|[^a-z])(install|installer|setup|updater|update|launcher|assistant|remoteassist|pageant)([^a-z]|$)'
        THEN 'installer_or_admin_tool'
      WHEN LOWER(sample_label) REGEXP '(^|[^a-z])(uninstall)([^a-z]|$)'
        THEN 'uninstall_utility'
      WHEN LOWER(sample_label) REGEXP '\\.(exe|dll|zip|jar|doc|png|apk|virus)$'
        THEN 'filename_extension'
      WHEN LOWER(sample_label) REGEXP '^[a-z0-9._+-]+$' AND sample_label LIKE '%.%'
        THEN 'package_or_hash_like'
      WHEN LOWER(sample_label) REGEXP 'phishing|unknown|unclassified|banker trojan'
        THEN 'generic_detection_name'
      ELSE 'other'
    END AS regex_bucket
  FROM fp
),
joint_counts AS (
  SELECT platform, regex_bucket, COUNT(*) AS n_xy
  FROM bucketed
  GROUP BY platform, regex_bucket
),
x_counts AS (
  SELECT platform, SUM(n_xy) AS n_x
  FROM joint_counts
  GROUP BY platform
),
y_counts AS (
  SELECT regex_bucket, SUM(n_xy) AS n_y
  FROM joint_counts
  GROUP BY regex_bucket
),
totals AS (
  SELECT SUM(n_xy) AS n_total
  FROM joint_counts
)
SELECT
  'effective_fp_platform_vs_regex_bucket_mi' AS metric_name,
  ROUND(SUM(
    (n_xy / n_total) * LOG((n_xy * n_total) / (n_x * n_y)) / LOG(2)
  ), 4) AS mutual_information_bits
FROM joint_counts j
JOIN x_counts x
  ON x.platform = j.platform
JOIN y_counts y
  ON y.regex_bucket = j.regex_bucket
CROSS JOIN totals;

-- 6. Remaining effective FP review concentration by label.
WITH counts AS (
  SELECT sample_label, COUNT(*) AS n
  FROM v_vt_false_positive_review_candidates_effective
  GROUP BY sample_label
),
ranked AS (
  SELECT
    sample_label,
    n,
    ROW_NUMBER() OVER (ORDER BY n DESC, sample_label) AS rn
  FROM counts
),
total AS (
  SELECT SUM(n) AS total_n, COUNT(*) AS k
  FROM counts
)
SELECT
  'effective_fp_labels' AS surface_name,
  total_n,
  k AS distinct_items,
  ROUND(SUM(-(n / total_n) * LOG(n / total_n) / LOG(2)), 4) AS entropy_bits,
  ROUND(SUM(-(n / total_n) * LOG(n / total_n) / LOG(2)) / NULLIF((LOG(k) / LOG(2)), 0), 4) AS normalized_entropy,
  ROUND(SUM(POW(n / total_n, 2)), 4) AS hhi,
  ROUND(SUM((n / total_n) * LOG((n / total_n) * k) / LOG(2)), 4) AS theil_t_bits,
  ROUND(SUM(CASE WHEN rn <= 1 THEN n ELSE 0 END) / total_n, 4) AS top1_share,
  ROUND(SUM(CASE WHEN rn <= 3 THEN n ELSE 0 END) / total_n, 4) AS top3_share,
  ROUND(SUM(CASE WHEN rn <= 5 THEN n ELSE 0 END) / total_n, 4) AS top5_share
FROM ranked
CROSS JOIN total;

-- 7. Ranked lift table for missing-resolution package prefixes.
WITH miss AS (
  SELECT
    CASE
      WHEN c.android_package_name IS NULL OR TRIM(c.android_package_name) = '' THEN '<blank>'
      WHEN c.android_package_name LIKE '%.%' THEN SUBSTRING_INDEX(c.android_package_name, '.', 2)
      ELSE c.android_package_name
    END AS pkg_prefix
  FROM malware_sample_catalog c
  JOIN v_android_sample_family_type_authority a
    ON a.sample_id = c.sample_id
  WHERE a.authority_bucket = 'missing_resolved_family'
),
base AS (
  SELECT
    CASE
      WHEN android_package_name IS NULL OR TRIM(android_package_name) = '' THEN '<blank>'
      WHEN android_package_name LIKE '%.%' THEN SUBSTRING_INDEX(android_package_name, '.', 2)
      ELSE android_package_name
    END AS pkg_prefix
  FROM malware_sample_catalog
  WHERE platform = 'android' AND file_extension = 'apk'
),
miss_counts AS (
  SELECT pkg_prefix, COUNT(*) AS miss_n
  FROM miss
  GROUP BY pkg_prefix
),
base_counts AS (
  SELECT pkg_prefix, COUNT(*) AS base_n
  FROM base
  GROUP BY pkg_prefix
),
totals AS (
  SELECT
    (SELECT COUNT(*) FROM miss) AS miss_total,
    (SELECT COUNT(*) FROM base) AS base_total
)
SELECT
  m.pkg_prefix,
  m.miss_n,
  b.base_n,
  ROUND(m.miss_n / miss_total, 4) AS miss_share,
  ROUND(b.base_n / base_total, 4) AS base_share,
  ROUND((m.miss_n / miss_total) / NULLIF((b.base_n / base_total), 0), 2) AS raw_lift,
  ROUND(((m.miss_n / miss_total) / NULLIF((b.base_n / base_total), 0)) * LOG(1 + m.miss_n), 2) AS support_weighted_lift
FROM miss_counts m
JOIN base_counts b
  ON b.pkg_prefix = m.pkg_prefix
CROSS JOIN totals
ORDER BY support_weighted_lift DESC, m.miss_n DESC, m.pkg_prefix;
