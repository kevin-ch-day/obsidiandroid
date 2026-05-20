-- Current-safe deep audit for family/type authority and temporal skew.
--
-- Scope:
--   - read-only
--   - built on the live Erebus view:
--       v_android_sample_family_type_authority
--   - no dependency on future label-authority foundation tables
--
-- Run from the target schema, for example:
--   mysql -t -D erebus_threat_intel_prod < database/sql/current_authority_temporal_gap_audit.sql
--
-- Key questions:
--   1) How complete is authority coverage now?
--   2) Which unresolved family tokens are likely real curation candidates?
--   3) Which authority families still need type curation?
--   4) Where do raw catalog type labels conflict with authority?
--   5) How temporally concentrated are the current families/types?

SET NAMES utf8mb4;

-- -----------------------------------------------------------------------------
-- Q1) Authority bucket summary
-- -----------------------------------------------------------------------------
SELECT
    authority_bucket,
    COUNT(*) AS sample_rows,
    COUNT(
        DISTINCT COALESCE(
            NULLIF(family_slug, ''),
            NULLIF(resolved_family_lc, ''),
            '<none>'
        )
    ) AS distinct_family_tokens
FROM v_android_sample_family_type_authority
GROUP BY authority_bucket
ORDER BY sample_rows DESC, authority_bucket ASC;

-- -----------------------------------------------------------------------------
-- Q2) Authority coverage by year
-- -----------------------------------------------------------------------------
SELECT
    YEAR(vt_first_submission_at_utc) AS yr,
    COUNT(*) AS total_rows,
    SUM(authority_bucket = 'authority_family_typed') AS typed_rows,
    SUM(authority_bucket = 'authority_family_unknown_type') AS unknown_type_rows,
    SUM(authority_bucket = 'resolved_but_no_authority_family') AS unresolved_family_rows,
    SUM(authority_bucket = 'generic_label_candidate') AS generic_rows,
    SUM(authority_bucket = 'resolved_unknown') AS unknown_rows,
    ROUND(
        100 * SUM(authority_bucket = 'authority_family_typed') / NULLIF(COUNT(*), 0),
        2
    ) AS typed_pct
FROM v_android_sample_family_type_authority
GROUP BY YEAR(vt_first_submission_at_utc)
ORDER BY yr ASC;

-- -----------------------------------------------------------------------------
-- Q3) Missing authority-family candidates
-- -----------------------------------------------------------------------------
SELECT
    resolved_family_lc,
    authority_gap_reason,
    COUNT(*) AS sample_rows,
    COUNT(DISTINCT NULLIF(android_package_name, '')) AS package_count,
    MIN(YEAR(vt_first_submission_at_utc)) AS first_year,
    MAX(YEAR(vt_first_submission_at_utc)) AS last_year
FROM v_android_sample_family_type_authority
WHERE authority_bucket = 'resolved_but_no_authority_family'
GROUP BY resolved_family_lc, authority_gap_reason
ORDER BY sample_rows DESC, resolved_family_lc ASC
LIMIT 200;

-- -----------------------------------------------------------------------------
-- Q4) Generic / coarse label candidates
-- -----------------------------------------------------------------------------
SELECT
    resolved_family_lc,
    COUNT(*) AS sample_rows,
    COUNT(DISTINCT NULLIF(android_package_name, '')) AS package_count,
    MIN(YEAR(vt_first_submission_at_utc)) AS first_year,
    MAX(YEAR(vt_first_submission_at_utc)) AS last_year
FROM v_android_sample_family_type_authority
WHERE authority_bucket = 'generic_label_candidate'
GROUP BY resolved_family_lc
ORDER BY sample_rows DESC, resolved_family_lc ASC
LIMIT 200;

-- -----------------------------------------------------------------------------
-- Q5) Authority families with unknown type
-- -----------------------------------------------------------------------------
SELECT
    family_slug,
    family_name,
    COUNT(*) AS sample_rows,
    MIN(YEAR(vt_first_submission_at_utc)) AS first_year,
    MAX(YEAR(vt_first_submission_at_utc)) AS last_year,
    GROUP_CONCAT(
        DISTINCT NULLIF(raw_classification_primary, '')
        ORDER BY raw_classification_primary
        SEPARATOR ', '
    ) AS raw_primary_hints,
    GROUP_CONCAT(
        DISTINCT NULLIF(raw_classification_subtype, '')
        ORDER BY raw_classification_subtype
        SEPARATOR ', '
    ) AS raw_subtype_hints
FROM v_android_sample_family_type_authority
WHERE authority_bucket = 'authority_family_unknown_type'
GROUP BY family_slug, family_name
ORDER BY sample_rows DESC, family_slug ASC
LIMIT 200;

-- -----------------------------------------------------------------------------
-- Q6) Raw-vs-authority conflict hotspots
-- -----------------------------------------------------------------------------
SELECT
    family_slug,
    type_slug,
    raw_classification_primary,
    raw_classification_subtype,
    COUNT(*) AS sample_rows
FROM v_android_sample_family_type_authority
WHERE raw_vs_authority_status = 'raw_conflicts_with_authority'
GROUP BY
    family_slug,
    type_slug,
    raw_classification_primary,
    raw_classification_subtype
ORDER BY sample_rows DESC, family_slug ASC
LIMIT 200;

-- -----------------------------------------------------------------------------
-- Q7) Family time concentration
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
        MAX(n) AS max_single_year_samples
    FROM family_year
    GROUP BY family_slug, type_slug
)
SELECT
    family_slug,
    type_slug,
    total_samples,
    active_years,
    ROUND(
        100 * max_single_year_samples / NULLIF(total_samples, 0),
        2
    ) AS max_single_year_pct
FROM family_rollup
WHERE total_samples >= 5
ORDER BY max_single_year_pct DESC, total_samples DESC, family_slug ASC
LIMIT 200;

-- -----------------------------------------------------------------------------
-- Q8) Year/type concentration for authority-typed samples
-- -----------------------------------------------------------------------------
SELECT
    YEAR(vt_first_submission_at_utc) AS yr,
    type_slug,
    COUNT(*) AS sample_rows,
    COUNT(DISTINCT family_slug) AS family_count
FROM v_android_sample_family_type_authority
WHERE authority_bucket = 'authority_family_typed'
GROUP BY YEAR(vt_first_submission_at_utc), type_slug
ORDER BY yr ASC, sample_rows DESC, type_slug ASC;
