-- Current-safe benchmark feasibility audit for ObsidianDroid.
--
-- Scope:
--   - read-only
--   - built on v_android_sample_family_type_authority
--   - helps answer whether current family/type evaluation claims are supportable
--     under support thresholds and temporal split constraints.
--
-- Run from the target schema, for example:
--   mysql -t -D erebus_threat_intel_prod < database/sql/current_benchmark_feasibility_audit.sql

SET NAMES utf8mb4;

-- -----------------------------------------------------------------------------
-- Q1) Family persistence summary
-- -----------------------------------------------------------------------------
WITH family_year AS (
    SELECT
        family_slug,
        type_slug,
        YEAR(vt_first_submission_at_utc) AS yr,
        COUNT(*) AS n
    FROM v_android_sample_family_type_authority
    WHERE authority_bucket = 'authority_family_typed'
      AND COALESCE(family_slug, '') <> ''
      AND vt_first_submission_at_utc IS NOT NULL
    GROUP BY family_slug, type_slug, YEAR(vt_first_submission_at_utc)
),
family_rollup AS (
    SELECT
        family_slug,
        type_slug,
        SUM(n) AS total_samples,
        COUNT(*) AS active_years,
        MIN(yr) AS first_year,
        MAX(yr) AS last_year,
        MIN(n) AS min_year_support,
        MAX(n) AS max_year_support
    FROM family_year
    GROUP BY family_slug, type_slug
)
SELECT
    family_slug,
    type_slug,
    total_samples,
    active_years,
    first_year,
    last_year,
    min_year_support,
    max_year_support
FROM family_rollup
ORDER BY active_years DESC, total_samples DESC, family_slug ASC;

-- -----------------------------------------------------------------------------
-- Q2) Global support-threshold preview
-- -----------------------------------------------------------------------------
WITH family_support AS (
    SELECT
        family_slug,
        type_slug,
        COUNT(*) AS n
    FROM v_android_sample_family_type_authority
    WHERE authority_bucket = 'authority_family_typed'
    GROUP BY family_slug, type_slug
)
SELECT
    SUM(n >= 3) AS families_ge_3,
    SUM(n >= 5) AS families_ge_5,
    SUM(n >= 10) AS families_ge_10,
    SUM(n >= 20) AS families_ge_20,
    SUM(n >= 30) AS families_ge_30,
    SUM(n >= 50) AS families_ge_50,
    COUNT(*) AS total_authority_typed_families
FROM family_support;

-- -----------------------------------------------------------------------------
-- Q3) Task shape by type after authority typing
-- -----------------------------------------------------------------------------
WITH family_support AS (
    SELECT
        type_slug,
        family_slug,
        COUNT(*) AS n
    FROM v_android_sample_family_type_authority
    WHERE authority_bucket = 'authority_family_typed'
    GROUP BY type_slug, family_slug
)
SELECT
    type_slug,
    SUM(n) AS type_rows,
    COUNT(*) AS family_count,
    SUM(CASE WHEN n >= 20 THEN 1 ELSE 0 END) AS families_ge_20,
    SUM(CASE WHEN n >= 10 THEN 1 ELSE 0 END) AS families_ge_10,
    SUM(CASE WHEN n >= 5 THEN 1 ELSE 0 END) AS families_ge_5
FROM family_support
GROUP BY type_slug
ORDER BY type_rows DESC, type_slug ASC;

-- -----------------------------------------------------------------------------
-- Q4) Single-family-type inflation under common support thresholds
-- -----------------------------------------------------------------------------
WITH family_support AS (
    SELECT
        type_slug,
        family_slug,
        COUNT(*) AS n
    FROM v_android_sample_family_type_authority
    WHERE authority_bucket = 'authority_family_typed'
    GROUP BY type_slug, family_slug
),
thresholds AS (
    SELECT 3 AS min_support UNION ALL
    SELECT 5 UNION ALL
    SELECT 10 UNION ALL
    SELECT 20 UNION ALL
    SELECT 30 UNION ALL
    SELECT 50
),
surviving AS (
    SELECT
        t.min_support,
        fs.type_slug,
        fs.family_slug,
        fs.n
    FROM thresholds AS t
    JOIN family_support AS fs
      ON fs.n >= t.min_support
),
type_rollup AS (
    SELECT
        min_support,
        type_slug,
        SUM(n) AS type_rows,
        COUNT(*) AS family_count
    FROM surviving
    GROUP BY min_support, type_slug
)
SELECT
    min_support,
    SUM(type_rows) AS surviving_rows,
    SUM(family_count) AS surviving_families,
    SUM(CASE WHEN family_count = 1 THEN type_rows ELSE 0 END) AS single_family_type_rows,
    ROUND(
        100 * SUM(CASE WHEN family_count = 1 THEN type_rows ELSE 0 END) / NULLIF(SUM(type_rows), 0),
        2
    ) AS single_family_type_row_pct,
    SUM(CASE WHEN family_count = 1 THEN 1 ELSE 0 END) AS single_family_type_count
FROM type_rollup
GROUP BY min_support
ORDER BY min_support ASC;

-- -----------------------------------------------------------------------------
-- Q5) Family-persistence-only benchmark headroom
-- -----------------------------------------------------------------------------
WITH family_year AS (
    SELECT
        family_slug,
        type_slug,
        YEAR(vt_first_submission_at_utc) AS yr,
        COUNT(*) AS n
    FROM v_android_sample_family_type_authority
    WHERE authority_bucket = 'authority_family_typed'
      AND vt_first_submission_at_utc IS NOT NULL
    GROUP BY family_slug, type_slug, YEAR(vt_first_submission_at_utc)
),
family_rollup AS (
    SELECT
        family_slug,
        type_slug,
        COUNT(*) AS active_years,
        MIN(n) AS min_year_support,
        SUM(n) AS total_samples
    FROM family_year
    GROUP BY family_slug, type_slug
)
SELECT
    SUM(active_years >= 2) AS families_ge_2_years,
    SUM(active_years >= 3) AS families_ge_3_years,
    SUM(active_years >= 2 AND min_year_support >= 3) AS families_ge_2_years_min3,
    SUM(active_years >= 2 AND min_year_support >= 5) AS families_ge_2_years_min5,
    SUM(active_years >= 3 AND min_year_support >= 3) AS families_ge_3_years_min3,
    SUM(active_years >= 3 AND min_year_support >= 5) AS families_ge_3_years_min5
FROM family_rollup;

-- -----------------------------------------------------------------------------
-- Q6) Families surviving a strict persistence rule (>=3 years, >=5 per year)
-- -----------------------------------------------------------------------------
WITH family_year AS (
    SELECT
        family_slug,
        type_slug,
        YEAR(vt_first_submission_at_utc) AS yr,
        COUNT(*) AS n
    FROM v_android_sample_family_type_authority
    WHERE authority_bucket = 'authority_family_typed'
      AND vt_first_submission_at_utc IS NOT NULL
    GROUP BY family_slug, type_slug, YEAR(vt_first_submission_at_utc)
),
family_rollup AS (
    SELECT
        family_slug,
        type_slug,
        COUNT(*) AS active_years,
        MIN(n) AS min_year_support,
        SUM(n) AS total_samples
    FROM family_year
    GROUP BY family_slug, type_slug
)
SELECT
    family_slug,
    type_slug,
    active_years,
    min_year_support,
    total_samples
FROM family_rollup
WHERE active_years >= 3
  AND min_year_support >= 5
ORDER BY type_slug ASC, total_samples DESC, family_slug ASC;

-- -----------------------------------------------------------------------------
-- Q7) Example temporal split feasibility windows
-- -----------------------------------------------------------------------------
WITH family_year AS (
    SELECT
        family_slug,
        type_slug,
        YEAR(vt_first_submission_at_utc) AS yr,
        COUNT(*) AS n
    FROM v_android_sample_family_type_authority
    WHERE authority_bucket = 'authority_family_typed'
      AND vt_first_submission_at_utc IS NOT NULL
    GROUP BY family_slug, type_slug, YEAR(vt_first_submission_at_utc)
),
family_rollup AS (
    SELECT
        family_slug,
        type_slug,
        SUM(CASE WHEN yr BETWEEN 2019 AND 2021 THEN n ELSE 0 END) AS train_2019_2021,
        SUM(CASE WHEN yr = 2022 THEN n ELSE 0 END) AS val_2022,
        SUM(CASE WHEN yr BETWEEN 2023 AND 2025 THEN n ELSE 0 END) AS test_2023_2025,
        SUM(CASE WHEN yr BETWEEN 2022 AND 2023 THEN n ELSE 0 END) AS train_2022_2023,
        SUM(CASE WHEN yr = 2024 THEN n ELSE 0 END) AS val_2024,
        SUM(CASE WHEN yr BETWEEN 2025 AND 2026 THEN n ELSE 0 END) AS test_2025_2026
    FROM family_year
    GROUP BY family_slug, type_slug
)
SELECT
    SUM(train_2019_2021 >= 5 AND val_2022 >= 3 AND test_2023_2025 >= 5) AS families_for_2019_2025_split,
    SUM(train_2022_2023 >= 5 AND val_2024 >= 3 AND test_2025_2026 >= 5) AS families_for_2022_2026_split,
    COUNT(*) AS authority_typed_families
FROM family_rollup;

-- -----------------------------------------------------------------------------
-- Q8) Which families survive the 2019-2025 example split?
-- -----------------------------------------------------------------------------
WITH family_year AS (
    SELECT
        family_slug,
        type_slug,
        YEAR(vt_first_submission_at_utc) AS yr,
        COUNT(*) AS n
    FROM v_android_sample_family_type_authority
    WHERE authority_bucket = 'authority_family_typed'
      AND vt_first_submission_at_utc IS NOT NULL
    GROUP BY family_slug, type_slug, YEAR(vt_first_submission_at_utc)
),
family_rollup AS (
    SELECT
        family_slug,
        type_slug,
        SUM(CASE WHEN yr BETWEEN 2019 AND 2021 THEN n ELSE 0 END) AS train_2019_2021,
        SUM(CASE WHEN yr = 2022 THEN n ELSE 0 END) AS val_2022,
        SUM(CASE WHEN yr BETWEEN 2023 AND 2025 THEN n ELSE 0 END) AS test_2023_2025
    FROM family_year
    GROUP BY family_slug, type_slug
)
SELECT
    family_slug,
    type_slug,
    train_2019_2021,
    val_2022,
    test_2023_2025
FROM family_rollup
WHERE train_2019_2021 >= 5
  AND val_2022 >= 3
  AND test_2023_2025 >= 5
ORDER BY type_slug ASC, family_slug ASC;
