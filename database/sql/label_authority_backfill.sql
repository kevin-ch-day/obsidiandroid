-- Label authority backfill helpers.
--
-- Use this only after `label_authority_foundation.sql` has been applied.
-- The goal is to seed the new authority objects from current Erebus truth without
-- changing existing sample labels or runtime behavior.
--
-- This script intentionally focuses on safe first population steps:
--   1. self-alias seed from active canonical families
--   2. optional alias import from legacy alias tables
--   3. sample-level authority seed from current resolved family view

SET NAMES utf8mb4;
SET collation_connection = 'utf8mb4_unicode_ci';

-- ---------------------------------------------------------------------------
-- Step 1: seed canonical self-aliases from active family taxonomy.
-- ---------------------------------------------------------------------------
INSERT INTO malware_family_alias_fact (
    alias_token,
    canonical_family_slug,
    alias_kind,
    source_system,
    source_reference,
    confidence_score,
    is_active,
    notes
)
SELECT
    LOWER(TRIM(f.family_slug)) AS alias_token,
    LOWER(TRIM(f.family_slug)) AS canonical_family_slug,
    'canonical_slug' AS alias_kind,
    'erebus' AS source_system,
    'android_malware_family.family_slug' AS source_reference,
    1.0000 AS confidence_score,
    1 AS is_active,
    'seeded self-alias from active canonical family slug' AS notes
FROM android_malware_family AS f
WHERE f.is_active = 1
  AND COALESCE(TRIM(f.family_slug), '') <> ''
ON DUPLICATE KEY UPDATE
    confidence_score = VALUES(confidence_score),
    updated_at_utc = CURRENT_TIMESTAMP;

INSERT INTO malware_family_alias_fact (
    alias_token,
    canonical_family_slug,
    alias_kind,
    source_system,
    source_reference,
    confidence_score,
    is_active,
    notes
)
SELECT
    LOWER(TRIM(f.family_name)) AS alias_token,
    LOWER(TRIM(f.family_slug)) AS canonical_family_slug,
    'canonical_name' AS alias_kind,
    'erebus' AS source_system,
    'android_malware_family.family_name' AS source_reference,
    0.9500 AS confidence_score,
    1 AS is_active,
    'seeded direct family-name alias from active canonical family name' AS notes
FROM android_malware_family AS f
WHERE f.is_active = 1
  AND COALESCE(TRIM(f.family_name), '') <> ''
  AND COALESCE(TRIM(f.family_slug), '') <> ''
ON DUPLICATE KEY UPDATE
    confidence_score = GREATEST(COALESCE(confidence_score, 0), VALUES(confidence_score)),
    updated_at_utc = CURRENT_TIMESTAMP;

-- ---------------------------------------------------------------------------
-- Step 2: optional import from a legacy alias table if present.
--
-- This repository references `android_malware_family_alias` in older audits, but
-- not every Erebus deployment may expose it. Run this block only when that table
-- exists and the operator has reviewed its contents.
-- ---------------------------------------------------------------------------
-- INSERT INTO malware_family_alias_fact (
--     alias_token,
--     canonical_family_slug,
--     alias_kind,
--     source_system,
--     source_reference,
--     confidence_score,
--     is_active,
--     notes
-- )
-- SELECT
--     LOWER(TRIM(a.alias_name)) AS alias_token,
--     LOWER(TRIM(f.family_slug)) AS canonical_family_slug,
--     'legacy_alias_table' AS alias_kind,
--     'erebus' AS source_system,
--     'android_malware_family_alias.alias_name' AS source_reference,
--     0.9000 AS confidence_score,
--     1 AS is_active,
--     'seeded from legacy android_malware_family_alias table' AS notes
-- FROM android_malware_family_alias AS a
-- JOIN android_malware_family AS f
--   ON f.family_id = a.family_id
-- WHERE f.is_active = 1
--   AND COALESCE(TRIM(a.alias_name), '') <> ''
--   AND COALESCE(TRIM(f.family_slug), '') <> ''
-- ON DUPLICATE KEY UPDATE
--     confidence_score = GREATEST(COALESCE(confidence_score, 0), VALUES(confidence_score)),
--     updated_at_utc = CURRENT_TIMESTAMP;

-- ---------------------------------------------------------------------------
-- Step 3: seed sample-level governed authority from current resolved family view.
--
-- History model:
--   - one active row per sample
--   - inactive rows preserve prior governed-family decisions
--   - exact content matches are reactivated instead of duplicated
-- ---------------------------------------------------------------------------
DROP TEMPORARY TABLE IF EXISTS tmp_malware_family_authority_seed;
CREATE TEMPORARY TABLE tmp_malware_family_authority_seed
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci
AS
SELECT
    msc.sample_id,
    fam.family_id AS governed_family_id,
    LOWER(TRIM(fam.family_slug)) AS governed_family_slug,
    fam.family_name AS governed_family_name,
    typ.type_id AS governed_type_id,
    LOWER(TRIM(typ.type_slug)) AS governed_type_slug,
    'erebus' AS authority_source_system,
    'v_android_apk_family_resolved' AS authority_source_table,
    'resolved_family_lc_join' AS authority_resolution_method,
    'bootstrap_v1' AS authority_version,
    'auto' AS review_status,
    1 AS is_active,
    'seeded from current resolved family/type view' AS notes,
    SHA1(
        CONCAT_WS(
            '|',
            CAST(msc.sample_id AS CHAR),
            COALESCE(LOWER(TRIM(fam.family_slug)), ''),
            COALESCE(LOWER(TRIM(typ.type_slug)), ''),
            'erebus',
            'v_android_apk_family_resolved',
            'resolved_family_lc_join',
            'bootstrap_v1',
            'auto'
        )
    ) COLLATE utf8mb4_unicode_ci AS authority_content_sha1
FROM malware_sample_catalog AS msc
JOIN (
    SELECT sample_id, resolved_family_lc
    FROM (
        SELECT
            v0.sample_id,
            v0.resolved_family_lc,
            ROW_NUMBER() OVER (
                PARTITION BY v0.sample_id
                ORDER BY COALESCE(v0.resolved_family_lc, '') ASC, v0.sample_id ASC
            ) AS rn
        FROM v_android_apk_family_resolved AS v0
    ) AS ranked_family
    WHERE rn = 1
) AS fam_res
  ON fam_res.sample_id = msc.sample_id
JOIN android_malware_family AS fam
  ON LOWER(TRIM(fam.family_slug)) = fam_res.resolved_family_lc
 AND fam.is_active = 1
LEFT JOIN android_malware_type AS typ
  ON typ.type_id = fam.primary_type_id
WHERE COALESCE(TRIM(fam.family_slug), '') <> '';

UPDATE malware_family_authority_fact AS auth
JOIN tmp_malware_family_authority_seed AS seed
  ON seed.sample_id = auth.sample_id
SET auth.is_active = 0,
    auth.updated_at_utc = CURRENT_TIMESTAMP
WHERE auth.is_active = 1
  AND auth.authority_content_sha1 <> seed.authority_content_sha1;

UPDATE malware_family_authority_fact AS auth
JOIN tmp_malware_family_authority_seed AS seed
  ON auth.authority_content_sha1 = seed.authority_content_sha1
SET auth.is_active = 1,
    auth.updated_at_utc = CURRENT_TIMESTAMP
WHERE auth.is_active = 0;

INSERT INTO malware_family_authority_fact (
    sample_id,
    governed_family_id,
    governed_family_slug,
    governed_family_name,
    governed_type_id,
    governed_type_slug,
    authority_source_system,
    authority_source_table,
    authority_resolution_method,
    authority_version,
    review_status,
    is_active,
    notes
)
SELECT
    seed.sample_id,
    seed.governed_family_id,
    seed.governed_family_slug,
    seed.governed_family_name,
    seed.governed_type_id,
    seed.governed_type_slug,
    seed.authority_source_system,
    seed.authority_source_table,
    seed.authority_resolution_method,
    seed.authority_version,
    seed.review_status,
    seed.is_active,
    seed.notes
FROM tmp_malware_family_authority_seed AS seed
LEFT JOIN malware_family_authority_fact AS auth
  ON auth.authority_content_sha1 = seed.authority_content_sha1
WHERE auth.authority_id IS NULL;

-- ---------------------------------------------------------------------------
-- Step 4: optional operator sanity snapshot.
-- ---------------------------------------------------------------------------
SELECT 'malware_family_alias_fact' AS object_name, COUNT(*) AS row_count
FROM malware_family_alias_fact
UNION ALL
SELECT 'malware_family_authority_fact' AS object_name, COUNT(*) AS row_count
FROM malware_family_authority_fact;
