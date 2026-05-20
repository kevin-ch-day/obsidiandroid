-- Label authority audit queries.
--
-- These queries are intended for operators and researchers after the authority
-- foundation objects are populated.

SET NAMES utf8mb4;

-- 1. Samples where explicit authority overrides differ from catalog resolution.
SELECT
    larv.sample_id,
    larv.sha256,
    larv.catalog_family_slug,
    larv.governed_family_slug,
    larv.catalog_type_slug,
    larv.governed_type_slug,
    larv.authority_source_system,
    larv.authority_resolution_method,
    larv.review_status
FROM label_authority_resolution_view AS larv
WHERE larv.explicit_authority_override_flag = 1
  AND (
      COALESCE(larv.catalog_family_slug, '') <> COALESCE(larv.governed_family_slug, '')
      OR COALESCE(larv.catalog_type_slug, '') <> COALESCE(larv.governed_type_slug, '')
  )
ORDER BY larv.sample_id ASC;

-- 2. Alias entries that do not appear to map to an active catalog family slug.
SELECT
    afa.alias_token,
    afa.canonical_family_slug,
    afa.alias_kind,
    afa.source_system,
    afa.confidence_score
FROM malware_family_alias_fact AS afa
LEFT JOIN android_malware_family AS fam
    ON fam.family_slug = afa.canonical_family_slug
   AND fam.is_active = 1
WHERE afa.is_active = 1
  AND fam.family_id IS NULL
ORDER BY afa.canonical_family_slug ASC, afa.alias_token ASC;

-- 3. Vendor evidence dominated by generic tokens.
SELECT
    e.vendor_key,
    COUNT(*) AS evidence_rows,
    SUM(CASE WHEN e.generic_token_flag = 1 THEN 1 ELSE 0 END) AS generic_rows,
    ROUND(
        SUM(CASE WHEN e.generic_token_flag = 1 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
        4
    ) AS generic_ratio
FROM malware_family_label_evidence AS e
WHERE e.is_active = 1
GROUP BY e.vendor_key
ORDER BY generic_ratio DESC, evidence_rows DESC;

-- 4. Samples with strong vendor disagreement on parsed family token.
SELECT
    e.sample_id,
    COUNT(*) AS vendor_rows,
    COUNT(DISTINCT COALESCE(e.parsed_family_token, '')) AS distinct_family_tokens,
    GROUP_CONCAT(DISTINCT COALESCE(e.parsed_family_token, '<empty>') ORDER BY COALESCE(e.parsed_family_token, '<empty>') SEPARATOR ', ') AS family_tokens
FROM malware_family_label_evidence AS e
WHERE e.is_active = 1
GROUP BY e.sample_id
HAVING COUNT(DISTINCT COALESCE(e.parsed_family_token, '')) >= 3
ORDER BY distinct_family_tokens DESC, vendor_rows DESC, e.sample_id ASC
LIMIT 200;

-- 5. Samples whose effective type authority is missing even though family authority is present.
SELECT
    larv.sample_id,
    larv.sha256,
    larv.effective_family_slug,
    larv.effective_type_slug,
    larv.temporal_anchor_source
FROM label_authority_resolution_view AS larv
WHERE COALESCE(larv.effective_family_slug, '') <> ''
  AND COALESCE(larv.effective_type_slug, '') = ''
ORDER BY larv.sample_id ASC;

-- 6. Samples missing any usable temporal anchor.
SELECT
    larv.sample_id,
    larv.sha256,
    larv.effective_family_slug,
    larv.temporal_anchor_source,
    larv.temporal_anchor_quality
FROM label_authority_resolution_view AS larv
WHERE larv.temporal_anchor_quality = 'missing'
ORDER BY larv.sample_id ASC;

-- 7. Engines with configured dependency metadata.
SELECT
    d.engine_a_vendor_key,
    d.engine_b_vendor_key,
    d.dependency_kind,
    d.strength_score,
    d.evidence_source
FROM av_engine_dependency_fact AS d
WHERE d.is_active = 1
ORDER BY d.engine_a_vendor_key ASC, d.engine_b_vendor_key ASC;
