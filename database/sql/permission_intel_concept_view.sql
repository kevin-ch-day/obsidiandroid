-- Permission Intel concept-resolution view contract.
--
-- The comparison below is intentionally case-sensitive.  `token_value` is
-- indexed with the database's normal collation, while `BINARY` applies the
-- existing exact-token semantics to the lookup value.  This preserves the
-- prior binary-cast behavior without wrapping the indexed token column in a
-- function, allowing `idx_concept_token_value` to be used as a ref lookup.
--
-- Validate this change against the live schema before deployment.  In
-- particular, compare result rows for the reporting query and retain the
-- previous SHOW CREATE VIEW output as the rollback statement.

CREATE OR REPLACE ALGORITHM=UNDEFINED SQL SECURITY DEFINER
VIEW vw_permission_vt_current_concepts AS
SELECT
    v.permission_string AS observed_token,
    v.permission_string AS raw_token,
    LCASE(TRIM(v.permission_string)) AS raw_token_norm,
    ct.token_role,
    ct.mapping_source,
    ct.rule_version,
    c.concept_id,
    c.canonical_token,
    c.concept_family,
    c.source_family_key,
    c.authority_scope,
    c.visibility_class,
    c.concept_status,
    c.protection_level,
    c.source_url,
    v.source_system,
    v.source_engine,
    v.andro_type,
    v.andro_short_desc,
    v.first_seen_at_utc,
    v.last_seen_at_utc,
    v.seen_count,
    v.last_sample_id,
    CASE
        WHEN ct.token_role = 'alias' THEN 'alias_to_concept'
        WHEN ct.token_role = 'canonical' THEN 'exact_concept'
        ELSE 'unresolved_raw'
    END AS resolution_semantics
FROM android_permission_enrich_vt_current AS v
LEFT JOIN android_permission_concept_token AS ct
  ON ct.token_value = BINARY v.permission_string
LEFT JOIN android_permission_concept AS c
  ON c.concept_id = ct.concept_id;
