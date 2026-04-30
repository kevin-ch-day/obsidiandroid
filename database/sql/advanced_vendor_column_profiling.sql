-- Advanced vendor-column profiling for virustotal_sample_vendor_engine_verdicts
-- Purpose:
--   1) Profile all vendor columns (coverage + distinct labels) for Android APK corpus
--   2) Profile all vendor columns for a curated taxonomy slice (type_slug = 'banker')
--   3) Surface columns with high signal but no parser coverage

USE erebus_database_dev;

SET SESSION group_concat_max_len = 1000000;

-- -----------------------------------------------------------------------------
-- Q1: Full Android APK corpus, all vendor columns
-- -----------------------------------------------------------------------------
SET @q1_sql = (
    SELECT GROUP_CONCAT(
        CONCAT(
            "SELECT '", column_name, "' AS vendor_col, ",
            "COUNT(*) AS total_rows, ",
            "SUM(CASE WHEN `", column_name, "` IS NOT NULL ",
            "AND TRIM(`", column_name, "`) <> '' ",
            "AND LOWER(TRIM(`", column_name, "`)) NOT IN ('none','null','n/a','undetected') ",
            "THEN 1 ELSE 0 END) AS non_empty_rows, ",
            "COUNT(DISTINCT CASE WHEN `", column_name, "` IS NOT NULL ",
            "AND TRIM(`", column_name, "`) <> '' ",
            "AND LOWER(TRIM(`", column_name, "`)) NOT IN ('none','null','n/a','undetected') ",
            "THEN LOWER(TRIM(`", column_name, "`)) END) AS distinct_labels ",
            "FROM virustotal_sample_vendor_engine_verdicts v ",
            "JOIN malware_sample_catalog m ON m.sample_id = v.sample_id ",
            "WHERE m.platform='android' AND m.file_extension='apk'"
        )
        SEPARATOR " UNION ALL "
    )
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'virustotal_sample_vendor_engine_verdicts'
      AND column_name NOT IN ('sample_id', 'updated_at')
);

SET @q1_sql = CONCAT(
    "SELECT vendor_col, total_rows, non_empty_rows, ",
    "ROUND(100 * non_empty_rows / NULLIF(total_rows,0), 2) AS coverage_pct, ",
    "distinct_labels ",
    "FROM (", @q1_sql, ") s ",
    "ORDER BY non_empty_rows DESC, distinct_labels DESC"
);

PREPARE stmt_q1 FROM @q1_sql;
EXECUTE stmt_q1;
DEALLOCATE PREPARE stmt_q1;

-- -----------------------------------------------------------------------------
-- Q2: Type-scoped profile (banker), all vendor columns
-- -----------------------------------------------------------------------------
SET @q2_sql = (
    SELECT GROUP_CONCAT(
        CONCAT(
            "SELECT '", column_name, "' AS vendor_col, ",
            "COUNT(*) AS total_rows, ",
            "SUM(CASE WHEN `", column_name, "` IS NOT NULL ",
            "AND TRIM(`", column_name, "`) <> '' ",
            "AND LOWER(TRIM(`", column_name, "`)) NOT IN ('none','null','n/a','undetected') ",
            "THEN 1 ELSE 0 END) AS non_empty_rows, ",
            "COUNT(DISTINCT CASE WHEN `", column_name, "` IS NOT NULL ",
            "AND TRIM(`", column_name, "`) <> '' ",
            "AND LOWER(TRIM(`", column_name, "`)) NOT IN ('none','null','n/a','undetected') ",
            "THEN LOWER(TRIM(`", column_name, "`)) END) AS distinct_labels ",
            "FROM virustotal_sample_vendor_engine_verdicts v ",
            "JOIN malware_sample_catalog m ON m.sample_id = v.sample_id ",
            "JOIN android_malware_family f ON LOWER(TRIM(m.family_label)) = LOWER(TRIM(f.family_name)) AND f.is_active=1 ",
            "JOIN android_malware_type t ON t.type_id = f.primary_type_id ",
            "WHERE m.platform='android' AND m.file_extension='apk' AND t.type_slug='banker'"
        )
        SEPARATOR " UNION ALL "
    )
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'virustotal_sample_vendor_engine_verdicts'
      AND column_name NOT IN ('sample_id', 'updated_at')
);

SET @q2_sql = CONCAT(
    "SELECT vendor_col, total_rows, non_empty_rows, ",
    "ROUND(100 * non_empty_rows / NULLIF(total_rows,0), 2) AS coverage_pct, ",
    "distinct_labels ",
    "FROM (", @q2_sql, ") s ",
    "ORDER BY non_empty_rows DESC, distinct_labels DESC"
);

PREPARE stmt_q2 FROM @q2_sql;
EXECUTE stmt_q2;
DEALLOCATE PREPARE stmt_q2;

-- -----------------------------------------------------------------------------
-- Q3: Join with vendor-engine flags for ranking context
-- -----------------------------------------------------------------------------
-- NOTE: Run after exporting Q1/Q2 if you want to combine in BI/Pandas.
SELECT
    LOWER(TRIM(vendor_key)) AS vendor_col,
    is_engine_active,
    is_trusted_vendor
FROM virustotal_vendor_engines
ORDER BY vendor_col;
