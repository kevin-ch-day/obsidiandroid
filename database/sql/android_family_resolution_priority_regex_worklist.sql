-- Read-only priority worklist for the live Android family-resolution gap.
--
-- Purpose:
--   * rank unresolved rows into practical remediation lanes using regex and
--     token-shape heuristics
--   * separate exact accepted-alias misses from true taxonomy contradictions
--   * surface repeated unresolved family/vt-token pairings that are likely to
--     justify the next bounded taxonomy repair tranche

SET NAMES utf8mb4;

-- 1. Priority lanes inside the fully unresolved review pool.
WITH unresolved AS (
    SELECT
        r.sample_id,
        COALESCE(c.android_package_name, '') AS android_package_name,
        COALESCE(c.family_label, '') AS family_label,
        COALESCE(c.vt_family_token, '') AS vt_family_token,
        LOWER(TRIM(COALESCE(c.family_label, ''))) AS family_label_norm,
        LOWER(TRIM(COALESCE(c.vt_family_token, ''))) AS vt_token_norm
    FROM vw_malware_sample_catalog_family_resolution_review AS r
    JOIN malware_sample_catalog AS c
      USING (sample_id)
    WHERE r.resolution_review_status IS NULL
      AND r.resolution_trust_tier IS NULL
),
accepted_alias_hits AS (
    SELECT DISTINCT
        u.sample_id
    FROM unresolved AS u
    JOIN android_malware_family_alias AS a
      ON u.family_label_norm = LOWER(a.alias_name)
    WHERE a.review_status = 'accepted'
),
contradiction_hits AS (
    SELECT DISTINCT
        u.sample_id
    FROM unresolved AS u
    JOIN android_malware_family_alias AS a
      ON u.family_label_norm = LOWER(a.alias_name)
    JOIN android_malware_family AS f
      ON f.family_id = a.family_id
    WHERE a.notes IS NOT NULL
      AND (
          (LOWER(a.notes) REGEXP 'brata|banbra' AND f.family_slug <> 'brata')
          OR (LOWER(a.notes) REGEXP 'cerberus' AND f.family_slug <> 'cerberus')
          OR (LOWER(a.notes) REGEXP 'terracotta|teracotta' AND f.family_slug <> 'terracotta')
          OR (LOWER(a.notes) REGEXP 'ubel' AND f.family_slug <> 'ubel')
      )
),
bucketed AS (
    SELECT
        u.sample_id,
        u.android_package_name,
        u.family_label,
        u.vt_family_token,
        CASE
            WHEN ah.sample_id IS NOT NULL THEN 'accepted_alias_mapping_gap'
            WHEN ch.sample_id IS NOT NULL THEN 'alias_family_contradiction'
            WHEN u.family_label_norm = '' THEN 'blank_catalog_family'
            WHEN u.family_label_norm REGEXP 'unknown|generic|unclass|unlabel' THEN 'generic_placeholder'
            WHEN u.family_label_norm = u.vt_token_norm
                 AND u.family_label_norm <> '' THEN 'exact_family_vt_pair'
            WHEN u.family_label_norm REGEXP '^[a-z][a-z0-9]+$'
                 AND u.vt_token_norm REGEXP '^[a-z][a-z0-9]+$'
                 AND u.vt_token_norm <> '' THEN 'compact_pair_manual_review'
            WHEN u.family_label_norm REGEXP 'spy|stalk|rat|bot|bank|loan|ransom|steal|cookie'
              OR u.vt_token_norm REGEXP 'spy|stalk|rat|bot|bank|loan|ransom|steal|cookie'
              THEN 'security_semantic_pair'
            ELSE 'other_unresolved_shape'
        END AS remediation_lane
    FROM unresolved AS u
    LEFT JOIN accepted_alias_hits AS ah
      ON ah.sample_id = u.sample_id
    LEFT JOIN contradiction_hits AS ch
      ON ch.sample_id = u.sample_id
)
SELECT
    remediation_lane,
    COUNT(*) AS row_count,
    COUNT(DISTINCT COALESCE(NULLIF(android_package_name, ''), '<blank>')) AS distinct_packages,
    GROUP_CONCAT(
        CONCAT(
            sample_id,
            ':',
            COALESCE(NULLIF(family_label, ''), '<blank>'),
            ' / ',
            COALESCE(NULLIF(vt_family_token, ''), '<blank>')
        )
        ORDER BY sample_id
        SEPARATOR ' | '
    ) AS examples
FROM bucketed
GROUP BY remediation_lane
ORDER BY row_count DESC, remediation_lane;

-- 2. Exact accepted-alias misses that should usually be handled before broader
-- regex-based manual review.
WITH unresolved AS (
    SELECT
        r.sample_id,
        COALESCE(c.android_package_name, '') AS android_package_name,
        COALESCE(c.family_label, '') AS family_label,
        COALESCE(c.vt_family_token, '') AS vt_family_token,
        LOWER(TRIM(COALESCE(c.family_label, ''))) AS family_label_norm
    FROM vw_malware_sample_catalog_family_resolution_review AS r
    JOIN malware_sample_catalog AS c
      USING (sample_id)
    WHERE r.resolution_review_status IS NULL
      AND r.resolution_trust_tier IS NULL
)
SELECT
    a.alias_name,
    f.family_slug,
    COUNT(*) AS unresolved_rows,
    COUNT(DISTINCT COALESCE(NULLIF(u.android_package_name, ''), '<blank>')) AS distinct_packages,
    GROUP_CONCAT(u.sample_id ORDER BY u.sample_id) AS sample_ids
FROM unresolved AS u
JOIN android_malware_family_alias AS a
  ON u.family_label_norm = LOWER(a.alias_name)
JOIN android_malware_family AS f
  ON f.family_id = a.family_id
WHERE a.review_status = 'accepted'
GROUP BY a.alias_name, f.family_slug
ORDER BY unresolved_rows DESC, a.alias_name, f.family_slug;

-- 3. Contradiction worklist: alias notes indicate a different canonical family
-- than the linked family row, and unresolved samples still use that alias.
WITH unresolved AS (
    SELECT
        r.sample_id,
        COALESCE(c.android_package_name, '') AS android_package_name,
        COALESCE(c.family_label, '') AS family_label,
        COALESCE(c.vt_family_token, '') AS vt_family_token,
        LOWER(TRIM(COALESCE(c.family_label, ''))) AS family_label_norm
    FROM vw_malware_sample_catalog_family_resolution_review AS r
    JOIN malware_sample_catalog AS c
      USING (sample_id)
    WHERE r.resolution_review_status IS NULL
      AND r.resolution_trust_tier IS NULL
)
SELECT
    a.alias_id,
    a.alias_name,
    f.family_slug AS linked_family_slug,
    a.alias_type,
    a.review_status,
    COUNT(*) AS unresolved_rows,
    GROUP_CONCAT(u.sample_id ORDER BY u.sample_id) AS sample_ids,
    a.notes
FROM unresolved AS u
JOIN android_malware_family_alias AS a
  ON u.family_label_norm = LOWER(a.alias_name)
JOIN android_malware_family AS f
  ON f.family_id = a.family_id
WHERE a.notes IS NOT NULL
  AND (
      (LOWER(a.notes) REGEXP 'brata|banbra' AND f.family_slug <> 'brata')
      OR (LOWER(a.notes) REGEXP 'cerberus' AND f.family_slug <> 'cerberus')
      OR (LOWER(a.notes) REGEXP 'terracotta|teracotta' AND f.family_slug <> 'terracotta')
      OR (LOWER(a.notes) REGEXP 'ubel' AND f.family_slug <> 'ubel')
  )
GROUP BY
    a.alias_id,
    a.alias_name,
    f.family_slug,
    a.alias_type,
    a.review_status,
    a.notes
ORDER BY unresolved_rows DESC, a.alias_name;

-- 4. Repeated unresolved family/vt-token pairs. This is the most direct
-- regex-driven shortlist for future bounded taxonomy tranches.
WITH unresolved AS (
    SELECT
        r.sample_id,
        COALESCE(c.android_package_name, '') AS android_package_name,
        LOWER(TRIM(COALESCE(c.family_label, ''))) AS family_label_norm,
        LOWER(TRIM(COALESCE(c.vt_family_token, ''))) AS vt_token_norm
    FROM vw_malware_sample_catalog_family_resolution_review AS r
    JOIN malware_sample_catalog AS c
      USING (sample_id)
    WHERE r.resolution_review_status IS NULL
      AND r.resolution_trust_tier IS NULL
),
paired AS (
    SELECT
        family_label_norm,
        vt_token_norm,
        COUNT(*) AS row_count,
        COUNT(DISTINCT COALESCE(NULLIF(android_package_name, ''), '<blank>')) AS distinct_packages,
        GROUP_CONCAT(sample_id ORDER BY sample_id) AS sample_ids
    FROM unresolved
    WHERE family_label_norm <> ''
      AND vt_token_norm <> ''
    GROUP BY family_label_norm, vt_token_norm
    HAVING COUNT(*) >= 2
)
SELECT
    family_label_norm,
    vt_token_norm,
    row_count,
    distinct_packages,
    sample_ids
FROM paired
ORDER BY row_count DESC, family_label_norm, vt_token_norm
LIMIT 100;
