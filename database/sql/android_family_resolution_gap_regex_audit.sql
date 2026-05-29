-- Read-only regex / morphology audit for the live Android family-resolution gap.
--
-- Purpose:
--   - profile the unresolved family-resolution pool by naming pattern
--   - surface exact alias-like candidates for governed taxonomy repair
--   - find package-cluster/provenance lanes that should be handled outside
--     family-taxonomy curation

SET NAMES utf8mb4;

-- 1. Topline family-resolution review posture.
SELECT
    COALESCE(resolution_review_status, '<null>') AS resolution_review_status,
    COALESCE(resolution_trust_tier, '<null>') AS resolution_trust_tier,
    COUNT(*) AS row_count
FROM vw_malware_sample_catalog_family_resolution_review
GROUP BY COALESCE(resolution_review_status, '<null>'),
         COALESCE(resolution_trust_tier, '<null>')
ORDER BY row_count DESC, resolution_review_status, resolution_trust_tier;

-- 2. Regex buckets for unresolved catalog family labels.
WITH unresolved AS (
    SELECT
        sample_id,
        COALESCE(family_label, '') AS family_label,
        COALESCE(vt_family_token, '') AS vt_family_token,
        COALESCE(sample_label, '') AS sample_label,
        COALESCE(android_package_name, '') AS android_package_name
    FROM malware_sample_catalog
    WHERE platform = 'android'
      AND file_extension = 'apk'
      AND sample_id IN (
          SELECT sample_id
          FROM vw_malware_sample_catalog_family_resolution_review
          WHERE resolution_review_status IS NULL
            AND resolution_trust_tier IS NULL
      )
),
bucketed AS (
    SELECT
        sample_id,
        family_label,
        vt_family_token,
        android_package_name,
        CASE
            WHEN LOWER(TRIM(family_label)) = '' THEN 'blank_family_label'
            WHEN LOWER(TRIM(family_label)) REGEXP 'unknown|generic|unclass|unlabel' THEN 'generic_placeholder'
            WHEN LOWER(TRIM(family_label)) REGEXP 'spy|stalk' THEN 'spy_stem'
            WHEN LOWER(TRIM(family_label)) REGEXP 'bank|loan|pay|wallet' THEN 'bank_or_finance_stem'
            WHEN LOWER(TRIM(family_label)) REGEXP 'ad|ads|hiddenad|shop' THEN 'ad_or_shop_stem'
            WHEN LOWER(TRIM(family_label)) REGEXP 'bot|rat|remote' THEN 'bot_or_rat_stem'
            WHEN LOWER(TRIM(family_label)) REGEXP 'lock|ransom' THEN 'ransom_stem'
            WHEN LOWER(TRIM(family_label)) REGEXP 'steal|thief|cookie' THEN 'steal_stem'
            WHEN LOWER(TRIM(family_label)) REGEXP '^[a-z][a-z0-9]+$' THEN 'compact_slug_like'
            WHEN LOWER(TRIM(family_label)) REGEXP '[[:space:]]' THEN 'contains_space'
            ELSE 'other_family_label_shape'
        END AS family_label_bucket
    FROM unresolved
)
SELECT
    family_label_bucket,
    COUNT(*) AS row_count,
    GROUP_CONCAT(
        CONCAT(sample_id, ':', COALESCE(NULLIF(family_label, ''), '<blank>'))
        ORDER BY sample_id
        SEPARATOR ' | '
    ) AS examples
FROM bucketed
GROUP BY family_label_bucket
ORDER BY row_count DESC, family_label_bucket;

-- 3. Regex buckets for unresolved VT family tokens.
WITH unresolved AS (
    SELECT
        sample_id,
        COALESCE(family_label, '') AS family_label,
        COALESCE(vt_family_token, '') AS vt_family_token
    FROM malware_sample_catalog
    WHERE platform = 'android'
      AND file_extension = 'apk'
      AND sample_id IN (
          SELECT sample_id
          FROM vw_malware_sample_catalog_family_resolution_review
          WHERE resolution_review_status IS NULL
            AND resolution_trust_tier IS NULL
      )
),
bucketed AS (
    SELECT
        sample_id,
        family_label,
        vt_family_token,
        CASE
            WHEN LOWER(TRIM(vt_family_token)) = '' THEN 'blank_vt_token'
            WHEN LOWER(TRIM(vt_family_token)) REGEXP 'unknown|generic|unclass|andr|android' THEN 'generic_vt_token'
            WHEN LOWER(TRIM(vt_family_token)) REGEXP 'spy|stalk' THEN 'spy_stem'
            WHEN LOWER(TRIM(vt_family_token)) REGEXP 'bank|loan|pay|wallet' THEN 'bank_or_finance_stem'
            WHEN LOWER(TRIM(vt_family_token)) REGEXP 'ad|ads|hiddenad|shop' THEN 'ad_or_shop_stem'
            WHEN LOWER(TRIM(vt_family_token)) REGEXP 'bot|rat|remote' THEN 'bot_or_rat_stem'
            WHEN LOWER(TRIM(vt_family_token)) REGEXP 'lock|ransom' THEN 'ransom_stem'
            WHEN LOWER(TRIM(vt_family_token)) REGEXP 'steal|thief|cookie' THEN 'steal_stem'
            WHEN LOWER(TRIM(vt_family_token)) REGEXP '^[a-z][a-z0-9]+$' THEN 'compact_slug_like'
            WHEN LOWER(TRIM(vt_family_token)) REGEXP '[[:space:]]' THEN 'contains_space'
            ELSE 'other_vt_token_shape'
        END AS vt_token_bucket
    FROM unresolved
)
SELECT
    vt_token_bucket,
    COUNT(*) AS row_count,
    GROUP_CONCAT(
        CONCAT(sample_id, ':', COALESCE(NULLIF(vt_family_token, ''), '<blank>'))
        ORDER BY sample_id
        SEPARATOR ' | '
    ) AS examples
FROM bucketed
GROUP BY vt_token_bucket
ORDER BY row_count DESC, vt_token_bucket;

-- 4. Accepted alias hit opportunities still missing resolved-family coverage.
SELECT
    LOWER(TRIM(c.family_label)) AS family_label_lc,
    a.alias_name,
    f.family_slug,
    COUNT(*) AS unresolved_rows,
    GROUP_CONCAT(c.sample_id ORDER BY c.sample_id) AS sample_ids
FROM malware_sample_catalog AS c
JOIN android_malware_family_alias AS a
  ON LOWER(TRIM(c.family_label)) = LOWER(a.alias_name)
JOIN android_malware_family AS f
  ON f.family_id = a.family_id
LEFT JOIN vw_malware_sample_catalog_family_resolution AS r
  ON r.sample_id = c.sample_id
WHERE c.platform = 'android'
  AND c.file_extension = 'apk'
  AND a.review_status = 'accepted'
  AND COALESCE(r.resolved_family_slug, '') = ''
GROUP BY LOWER(TRIM(c.family_label)), a.alias_name, f.family_slug
ORDER BY unresolved_rows DESC, family_label_lc, f.family_slug;

-- 5. Package-cluster concentration inside the unresolved pool.
SELECT
    COALESCE(NULLIF(android_package_name, ''), '<blank>') AS android_package_name,
    COUNT(*) AS row_count,
    COUNT(DISTINCT LOWER(TRIM(COALESCE(family_label, '')))) AS distinct_family_labels,
    COUNT(DISTINCT LOWER(TRIM(COALESCE(vt_family_token, '')))) AS distinct_vt_tokens,
    GROUP_CONCAT(sample_id ORDER BY sample_id) AS sample_ids
FROM malware_sample_catalog
WHERE platform = 'android'
  AND file_extension = 'apk'
  AND sample_id IN (
      SELECT sample_id
      FROM vw_malware_sample_catalog_family_resolution_review
      WHERE resolution_review_status IS NULL
        AND resolution_trust_tier IS NULL
  )
GROUP BY COALESCE(NULLIF(android_package_name, ''), '<blank>')
HAVING COUNT(*) >= 2
ORDER BY row_count DESC, android_package_name
LIMIT 100;

-- 6. Taxonomy-note contradiction scanner for alias rows. This is intentionally
-- heuristic and highlights rows whose notes mention a different canonical family
-- stem than the linked family slug.
SELECT
    a.alias_id,
    a.alias_name,
    f.family_slug,
    a.alias_type,
    a.review_status,
    a.trust_tier,
    a.confidence,
    a.notes
FROM android_malware_family_alias AS a
JOIN android_malware_family AS f
  ON f.family_id = a.family_id
WHERE a.notes IS NOT NULL
  AND (
      (LOWER(a.notes) REGEXP 'brata|banbra' AND f.family_slug <> 'brata')
      OR (LOWER(a.notes) REGEXP 'cerberus' AND f.family_slug <> 'cerberus')
      OR (LOWER(a.notes) REGEXP 'teracotta|terracotta' AND f.family_slug <> 'terracotta')
      OR (LOWER(a.notes) REGEXP 'ubel' AND f.family_slug <> 'ubel')
      OR (LOWER(a.notes) REGEXP 'spyloan' AND f.family_slug <> 'spyloan')
      OR (LOWER(a.notes) REGEXP 'basbanke' AND f.family_slug <> 'basbanke')
      OR (LOWER(a.notes) REGEXP 'wroba' AND f.family_slug <> 'wroba')
      OR (LOWER(a.notes) REGEXP 'hawkshaw' AND f.family_slug <> 'hawkshaw')
      OR (LOWER(a.notes) REGEXP 'guerrilla' AND f.family_slug <> 'guerrilla')
  )
ORDER BY a.alias_id;
