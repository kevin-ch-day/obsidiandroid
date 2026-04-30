-- Advanced deep-dive audit for ObsidianDroid Android malware dataset.
-- Focus:
--   1) Cross-table integrity
--   2) Taxonomy resolution coverage
--   3) Vendor label concentration/noise
--   4) Temporal drift
--   5) Package/family conflict patterns
--
-- Run with:
--   mysql -u root -D erebus_database_dev -t < database/sql/advanced_deep_data_audit.sql

USE erebus_database_dev;

SET SESSION group_concat_max_len = 1000000;

-- -----------------------------------------------------------------------------
-- Q1) Core integrity checks
-- -----------------------------------------------------------------------------
SELECT
  COUNT(*) AS n_android_apk,
  COUNT(DISTINCT sample_id) AS n_sample_ids,
  COUNT(DISTINCT sha256) AS n_sha,
  SUM(sha256 IS NULL OR LENGTH(sha256)<>64) AS bad_sha,
  SUM(family_label IS NULL OR TRIM(family_label)='') AS missing_family,
  SUM(android_package_name IS NULL OR TRIM(android_package_name)='') AS missing_pkg,
  SUM(vt_first_submission_at_utc IS NULL AND vt_first_seen_itw_date IS NULL) AS missing_time
FROM malware_sample_catalog
WHERE platform='android' AND file_extension='apk';

SELECT
  COUNT(*) AS n_verdict_rows,
  COUNT(DISTINCT sample_id) AS n_verdict_sample_ids
FROM virustotal_sample_vendor_engine_verdicts;

SELECT
  COUNT(*) AS n_scan_rows,
  COUNT(DISTINCT sample_id) AS n_scan_sample_ids
FROM virustotal_sample_scan_summary;

-- -----------------------------------------------------------------------------
-- Q2) Alias coverage effectiveness
-- -----------------------------------------------------------------------------
WITH base AS (
  SELECT sample_id, LOWER(TRIM(family_label)) AS family_lc
  FROM malware_sample_catalog
  WHERE platform='android' AND file_extension='apk'
    AND family_label IS NOT NULL AND TRIM(family_label)<>''
), mapped AS (
  SELECT b.sample_id, b.family_lc,
         COALESCE(f1.family_id, f2.family_id) AS family_id,
         CASE
           WHEN f1.family_id IS NOT NULL THEN 'direct'
           WHEN f2.family_id IS NOT NULL THEN 'alias'
           ELSE 'none'
         END AS map_mode
  FROM base b
  LEFT JOIN android_malware_family f1
    ON LOWER(TRIM(f1.family_name)) = b.family_lc
   AND f1.is_active=1
  LEFT JOIN android_malware_family_alias a
    ON LOWER(TRIM(a.alias_name)) = b.family_lc
  LEFT JOIN android_malware_family f2
    ON f2.family_id = a.family_id
   AND f2.is_active=1
)
SELECT
  COUNT(*) AS n_total,
  SUM(map_mode='direct') AS n_direct,
  SUM(map_mode='alias') AS n_alias_only,
  SUM(map_mode='none') AS n_unresolved
FROM mapped;

-- -----------------------------------------------------------------------------
-- Q3) Unresolved label queue after direct + alias mapping
-- -----------------------------------------------------------------------------
WITH base AS (
  SELECT sample_id, LOWER(TRIM(family_label)) AS family_lc
  FROM malware_sample_catalog
  WHERE platform='android' AND file_extension='apk'
    AND family_label IS NOT NULL AND TRIM(family_label)<>''
), mapped AS (
  SELECT b.family_lc,
         COALESCE(f1.family_id, f2.family_id) AS family_id
  FROM base b
  LEFT JOIN android_malware_family f1
    ON LOWER(TRIM(f1.family_name)) = b.family_lc
   AND f1.is_active=1
  LEFT JOIN android_malware_family_alias a
    ON LOWER(TRIM(a.alias_name)) = b.family_lc
  LEFT JOIN android_malware_family f2
    ON f2.family_id = a.family_id
   AND f2.is_active=1
)
SELECT family_lc, COUNT(*) AS n_samples
FROM mapped
WHERE family_id IS NULL
GROUP BY family_lc
ORDER BY n_samples DESC
LIMIT 200;

-- -----------------------------------------------------------------------------
-- Q4) Temporal drift in mapping quality
-- -----------------------------------------------------------------------------
WITH base AS (
  SELECT
    YEAR(COALESCE(CAST(vt_first_seen_itw_date AS DATETIME), vt_first_submission_at_utc, record_created_at_utc)) AS yr,
    LOWER(TRIM(family_label)) AS family_lc
  FROM malware_sample_catalog
  WHERE platform='android' AND file_extension='apk'
    AND family_label IS NOT NULL AND TRIM(family_label)<>''
), flags AS (
  SELECT
    b.yr,
    b.family_lc,
    CASE WHEN f.family_id IS NOT NULL AND f.is_active=1 THEN 1 ELSE 0 END AS is_curated,
    CASE WHEN b.family_lc IN ('unknown','trojan','adware','ransomware','spyware') THEN 1 ELSE 0 END AS is_generic
  FROM base b
  LEFT JOIN android_malware_family f
    ON LOWER(TRIM(f.family_name)) = b.family_lc
)
SELECT
  yr,
  COUNT(*) AS n_total,
  SUM(is_curated) AS n_curated,
  SUM(is_generic) AS n_generic,
  SUM(CASE WHEN is_curated=0 AND is_generic=0 THEN 1 ELSE 0 END) AS n_unmapped,
  ROUND(100*SUM(is_curated)/COUNT(*),2) AS curated_pct,
  ROUND(100*SUM(CASE WHEN is_curated=0 AND is_generic=0 THEN 1 ELSE 0 END)/COUNT(*),2) AS unmapped_pct
FROM flags
GROUP BY yr
ORDER BY yr;

-- -----------------------------------------------------------------------------
-- Q5) Package/family conflict audit (same package mapped to multiple families)
-- -----------------------------------------------------------------------------
SELECT
  android_package_name,
  COUNT(*) AS n_samples,
  COUNT(DISTINCT LOWER(TRIM(family_label))) AS n_families,
  GROUP_CONCAT(DISTINCT LOWER(TRIM(family_label)) ORDER BY LOWER(TRIM(family_label)) SEPARATOR ', ') AS families
FROM malware_sample_catalog
WHERE platform='android' AND file_extension='apk'
  AND android_package_name IS NOT NULL AND TRIM(android_package_name)<>''
  AND family_label IS NOT NULL AND TRIM(family_label)<>''
GROUP BY android_package_name
HAVING COUNT(DISTINCT LOWER(TRIM(family_label))) > 1
ORDER BY n_families DESC, n_samples DESC
LIMIT 200;

-- -----------------------------------------------------------------------------
-- Q6) VT scan summary signal coverage
-- -----------------------------------------------------------------------------
SELECT
  COUNT(*) AS n_rows,
  SUM(vt_suspicious_count > 0) AS suspicious_gt0,
  ROUND(100*SUM(vt_suspicious_count > 0)/COUNT(*),2) AS suspicious_gt0_pct,
  SUM(vt_reputation IS NOT NULL) AS reputation_present,
  SUM(vt_times_submitted IS NOT NULL) AS times_submitted_present,
  SUM(vt_unique_sources IS NOT NULL) AS unique_sources_present,
  SUM(vt_suggested_threat_label IS NOT NULL AND TRIM(vt_suggested_threat_label)<>'') AS suggested_label_present,
  SUM(vt_tags IS NOT NULL AND TRIM(vt_tags)<>'') AS tags_present
FROM virustotal_sample_scan_summary;

-- -----------------------------------------------------------------------------
-- Q7) Vendor concentration/noise profile for all engine columns (dynamic SQL)
-- -----------------------------------------------------------------------------
SET @profile_sql = (
  SELECT GROUP_CONCAT(
    CONCAT(
      "SELECT '", column_name, "' AS vendor_col, ",
      "COUNT(*) AS total_rows, ",
      "SUM(CASE WHEN `", column_name, "` IS NOT NULL AND TRIM(`", column_name, "`)<>'' AND LOWER(TRIM(`", column_name, "`)) NOT IN ('none','null','n/a') THEN 1 ELSE 0 END) AS non_empty_rows, ",
      "SUM(CASE WHEN `", column_name, "` IS NOT NULL AND TRIM(`", column_name, "`)<>'' AND LOWER(TRIM(`", column_name, "`)) REGEXP '(unknown|generic|undetected|agent)' THEN 1 ELSE 0 END) AS unknown_like_rows, ",
      "COUNT(DISTINCT CASE WHEN `", column_name, "` IS NOT NULL AND TRIM(`", column_name, "`)<>'' AND LOWER(TRIM(`", column_name, "`)) NOT IN ('none','null','n/a') THEN LOWER(TRIM(`", column_name, "`)) END) AS distinct_labels, ",
      "(SELECT x.label FROM (",
      "   SELECT LOWER(TRIM(v2.`", column_name, "`)) AS label, COUNT(*) AS cnt ",
      "   FROM virustotal_sample_vendor_engine_verdicts v2 ",
      "   JOIN malware_sample_catalog m2 ON m2.sample_id=v2.sample_id ",
      "   WHERE m2.platform='android' AND m2.file_extension='apk' ",
      "     AND v2.`", column_name, "` IS NOT NULL AND TRIM(v2.`", column_name, "`)<>'' ",
      "     AND LOWER(TRIM(v2.`", column_name, "`)) NOT IN ('none','null','n/a') ",
      "   GROUP BY LOWER(TRIM(v2.`", column_name, "`)) ORDER BY cnt DESC LIMIT 1",
      ") x) AS top_label, ",
      "(SELECT x.cnt FROM (",
      "   SELECT LOWER(TRIM(v2.`", column_name, "`)) AS label, COUNT(*) AS cnt ",
      "   FROM virustotal_sample_vendor_engine_verdicts v2 ",
      "   JOIN malware_sample_catalog m2 ON m2.sample_id=v2.sample_id ",
      "   WHERE m2.platform='android' AND m2.file_extension='apk' ",
      "     AND v2.`", column_name, "` IS NOT NULL AND TRIM(v2.`", column_name, "`)<>'' ",
      "     AND LOWER(TRIM(v2.`", column_name, "`)) NOT IN ('none','null','n/a') ",
      "   GROUP BY LOWER(TRIM(v2.`", column_name, "`)) ORDER BY cnt DESC LIMIT 1",
      ") x) AS top_label_count ",
      "FROM virustotal_sample_vendor_engine_verdicts v ",
      "JOIN malware_sample_catalog m ON m.sample_id=v.sample_id ",
      "WHERE m.platform='android' AND m.file_extension='apk'"
    )
    SEPARATOR " UNION ALL "
  )
  FROM information_schema.columns
  WHERE table_schema=DATABASE()
    AND table_name='virustotal_sample_vendor_engine_verdicts'
    AND column_name NOT IN ('sample_id','updated_at')
);

SET @profile_sql = CONCAT(
  "SELECT vendor_col,total_rows,non_empty_rows,ROUND(100*non_empty_rows/NULLIF(total_rows,0),2) AS coverage_pct,",
  "unknown_like_rows,ROUND(100*unknown_like_rows/NULLIF(non_empty_rows,0),2) AS unknown_like_pct,",
  "distinct_labels,top_label,top_label_count,ROUND(100*top_label_count/NULLIF(non_empty_rows,0),2) AS top_label_pct ",
  "FROM (", @profile_sql, ") p ",
  "ORDER BY coverage_pct DESC, top_label_pct DESC, distinct_labels ASC"
);

PREPARE stmt_profile FROM @profile_sql;
EXECUTE stmt_profile;
DEALLOCATE PREPARE stmt_profile;
