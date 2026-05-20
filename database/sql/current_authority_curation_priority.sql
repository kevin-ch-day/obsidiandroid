-- Current-safe curation-priority audit for family/type authority.
--
-- Scope:
--   - read-only
--   - built on v_android_sample_family_type_authority
--   - intended to rank which family/type curation tasks will buy the most value
--
-- Run from the target schema, for example:
--   mysql -t -D erebus_threat_intel_prod < database/sql/current_authority_curation_priority.sql

SET NAMES utf8mb4;

-- -----------------------------------------------------------------------------
-- Q1) Missing family authority candidates with simple priority signals
-- -----------------------------------------------------------------------------
WITH unresolved AS (
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
)
SELECT
    resolved_family_lc,
    authority_gap_reason,
    sample_rows,
    package_count,
    first_year,
    last_year,
    CASE
        WHEN sample_rows >= 8 THEN 'high'
        WHEN sample_rows >= 4 THEN 'medium'
        ELSE 'low'
    END AS sample_priority,
    CASE
        WHEN package_count >= 3 THEN 'multi_package'
        WHEN package_count = 2 THEN 'two_package'
        ELSE 'single_package'
    END AS package_spread,
    CASE
        WHEN authority_gap_reason = 'resolved_token_malformed_or_composite' THEN 'review_name_normalization'
        ELSE 'review_family_authority'
    END AS suggested_action
FROM unresolved
ORDER BY
    sample_rows DESC,
    package_count DESC,
    resolved_family_lc ASC;

-- -----------------------------------------------------------------------------
-- Q2) Generic/coarse label pressure that should not become family authority
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
ORDER BY sample_rows DESC, resolved_family_lc ASC;

-- -----------------------------------------------------------------------------
-- Q3) Unknown-type authority families with curation hints
-- -----------------------------------------------------------------------------
SELECT
    family_slug,
    family_name,
    COUNT(*) AS sample_rows,
    MIN(YEAR(vt_first_submission_at_utc)) AS first_year,
    MAX(YEAR(vt_first_submission_at_utc)) AS last_year,
    GROUP_CONCAT(
        DISTINCT COALESCE(raw_classification_primary, '<null>')
        ORDER BY raw_classification_primary
        SEPARATOR ', '
    ) AS raw_primary_hints,
    GROUP_CONCAT(
        DISTINCT COALESCE(raw_classification_subtype, '<null>')
        ORDER BY raw_classification_subtype
        SEPARATOR ', '
    ) AS raw_subtype_hints,
    CASE
        WHEN COUNT(*) >= 20 THEN 'high'
        WHEN COUNT(*) >= 6 THEN 'medium'
        ELSE 'low'
    END AS type_curation_priority
FROM v_android_sample_family_type_authority
WHERE authority_bucket = 'authority_family_unknown_type'
GROUP BY family_slug, family_name
ORDER BY sample_rows DESC, family_slug ASC;

-- -----------------------------------------------------------------------------
-- Q4) Raw-vs-authority conflict hotspots for targeted policy review
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
ORDER BY sample_rows DESC, family_slug ASC;
