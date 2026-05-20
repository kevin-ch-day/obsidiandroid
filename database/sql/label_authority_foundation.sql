-- Label authority foundation for Erebus / ObsidianDroid integration.
--
-- This script is intentionally additive and non-destructive.
-- It creates the first data-layer objects needed to separate:
--   1. governed family/type authority,
--   2. vendor label evidence,
--   3. generic token policy,
--   4. temporal anchor provenance.
--
-- It does NOT:
--   - rewrite existing family assignments,
--   - run label-cleaning,
--   - change ObsidianDroid training behavior.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS malware_family_alias_fact (
    alias_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    alias_token VARCHAR(255) NOT NULL,
    canonical_family_slug VARCHAR(255) NOT NULL,
    alias_kind VARCHAR(64) NOT NULL DEFAULT 'family_alias',
    source_system VARCHAR(64) NOT NULL DEFAULT 'erebus',
    source_reference VARCHAR(255) NULL,
    confidence_score DECIMAL(5,4) NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    notes TEXT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (alias_id),
    UNIQUE KEY uq_malware_family_alias_active (
        alias_token,
        canonical_family_slug,
        alias_kind,
        is_active
    ),
    KEY idx_malware_family_alias_canonical (canonical_family_slug),
    KEY idx_malware_family_alias_source (source_system, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS malware_family_authority_fact (
    authority_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sample_id INT UNSIGNED NOT NULL,
    governed_family_id INT NULL,
    governed_family_slug VARCHAR(255) NULL,
    governed_family_name VARCHAR(255) NULL,
    governed_type_id INT NULL,
    governed_type_slug VARCHAR(64) NULL,
    authority_source_system VARCHAR(64) NOT NULL DEFAULT 'erebus',
    authority_source_table VARCHAR(128) NOT NULL DEFAULT 'v_android_apk_family_resolved',
    authority_resolution_method VARCHAR(128) NOT NULL DEFAULT 'resolved_family_lc_join',
    authority_version VARCHAR(64) NULL,
    review_status VARCHAR(32) NOT NULL DEFAULT 'auto',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    notes TEXT NULL,
    resolved_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (authority_id),
    UNIQUE KEY uq_malware_family_authority_active (sample_id, is_active),
    KEY idx_malware_family_authority_family (governed_family_slug, is_active),
    KEY idx_malware_family_authority_type (governed_type_slug, is_active),
    KEY idx_malware_family_authority_review (review_status, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vendor_label_generic_token_fact (
    generic_token_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    vendor_key VARCHAR(128) NOT NULL,
    raw_token VARCHAR(255) NOT NULL,
    normalized_token VARCHAR(255) NOT NULL,
    token_kind VARCHAR(64) NOT NULL,
    generic_default_flag TINYINT(1) NOT NULL DEFAULT 0,
    source_system VARCHAR(64) NOT NULL DEFAULT 'erebus',
    source_reference VARCHAR(255) NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    notes TEXT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (generic_token_id),
    UNIQUE KEY uq_vendor_label_generic_token_active (
        vendor_key,
        normalized_token,
        token_kind,
        is_active
    ),
    KEY idx_vendor_label_generic_token_vendor (vendor_key, is_active),
    KEY idx_vendor_label_generic_token_kind (token_kind, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS av_engine_dependency_fact (
    dependency_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    engine_a_vendor_key VARCHAR(128) NOT NULL,
    engine_b_vendor_key VARCHAR(128) NOT NULL,
    dependency_kind VARCHAR(64) NOT NULL,
    strength_score DECIMAL(5,4) NULL,
    evidence_source VARCHAR(128) NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    notes TEXT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (dependency_id),
    UNIQUE KEY uq_av_engine_dependency_active (
        engine_a_vendor_key,
        engine_b_vendor_key,
        dependency_kind,
        is_active
    ),
    KEY idx_av_engine_dependency_a (engine_a_vendor_key, is_active),
    KEY idx_av_engine_dependency_b (engine_b_vendor_key, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS malware_family_label_evidence (
    evidence_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sample_id INT UNSIGNED NOT NULL,
    vendor_key VARCHAR(128) NOT NULL,
    raw_vendor_label VARCHAR(512) NOT NULL,
    parsed_family_token VARCHAR(255) NULL,
    parsed_type_token VARCHAR(128) NULL,
    parsed_class_token VARCHAR(128) NULL,
    generic_token_flag TINYINT(1) NOT NULL DEFAULT 0,
    parser_name VARCHAR(128) NOT NULL DEFAULT 'vendor_parser',
    parser_version VARCHAR(64) NULL,
    parser_confidence_score DECIMAL(5,4) NULL,
    source_report_date_utc DATETIME NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    notes TEXT NULL,
    created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (evidence_id),
    KEY idx_mfle_sample (sample_id, is_active),
    KEY idx_mfle_vendor (vendor_key, is_active),
    KEY idx_mfle_family (parsed_family_token, is_active),
    KEY idx_mfle_type (parsed_type_token, is_active),
    KEY idx_mfle_generic (generic_token_flag, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP VIEW IF EXISTS v_android_sample_temporal_resolved;
CREATE VIEW v_android_sample_temporal_resolved AS
SELECT
    msc.sample_id,
    msc.sha256,
    msc.vt_first_seen_itw_date,
    msc.vt_first_submission_at_utc,
    COALESCE(msc.vt_first_seen_itw_date, msc.vt_first_submission_at_utc) AS effective_first_seen_at_utc,
    CASE
        WHEN msc.vt_first_seen_itw_date IS NOT NULL THEN 'vt_first_seen_itw_date'
        WHEN msc.vt_first_submission_at_utc IS NOT NULL THEN 'vt_first_submission_at_utc'
        ELSE 'missing'
    END AS temporal_anchor_source,
    CASE
        WHEN msc.vt_first_seen_itw_date IS NOT NULL THEN 'preferred'
        WHEN msc.vt_first_submission_at_utc IS NOT NULL THEN 'fallback'
        ELSE 'missing'
    END AS temporal_anchor_quality
FROM malware_sample_catalog AS msc;

DROP VIEW IF EXISTS label_authority_resolution_view;
CREATE VIEW label_authority_resolution_view AS
SELECT
    msc.sample_id,
    msc.sha256,
    msc.sample_label,
    msc.family_label AS family_label_raw,
    msc.classification_primary,
    msc.classification_subtype,
    fam_res.resolved_family_lc AS resolved_family_slug_catalog,
    fam.family_id AS catalog_family_id,
    fam.family_slug AS catalog_family_slug,
    fam.family_name AS catalog_family_name,
    typ.type_id AS catalog_type_id,
    typ.type_slug AS catalog_type_slug,
    tsr.vt_first_seen_itw_date,
    tsr.vt_first_submission_at_utc,
    tsr.effective_first_seen_at_utc,
    tsr.temporal_anchor_source,
    tsr.temporal_anchor_quality,
    auth.authority_id,
    auth.governed_family_id,
    auth.governed_family_slug,
    auth.governed_family_name,
    auth.governed_type_id,
    auth.governed_type_slug,
    auth.authority_source_system,
    auth.authority_source_table,
    auth.authority_resolution_method,
    auth.authority_version,
    auth.review_status,
    CASE
        WHEN auth.authority_id IS NOT NULL THEN auth.governed_family_slug
        ELSE fam.family_slug
    END AS effective_family_slug,
    CASE
        WHEN auth.authority_id IS NOT NULL THEN auth.governed_family_name
        ELSE fam.family_name
    END AS effective_family_name,
    CASE
        WHEN auth.authority_id IS NOT NULL THEN auth.governed_type_slug
        ELSE typ.type_slug
    END AS effective_type_slug,
    CASE
        WHEN auth.authority_id IS NOT NULL THEN 1
        ELSE 0
    END AS explicit_authority_override_flag
FROM malware_sample_catalog AS msc
LEFT JOIN (
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
LEFT JOIN android_malware_family AS fam
    ON LOWER(fam.family_slug) = fam_res.resolved_family_lc
LEFT JOIN android_malware_type AS typ
    ON typ.type_id = fam.primary_type_id
LEFT JOIN v_android_sample_temporal_resolved AS tsr
    ON tsr.sample_id = msc.sample_id
LEFT JOIN (
    SELECT *
    FROM malware_family_authority_fact
    WHERE is_active = 1
) AS auth
    ON auth.sample_id = msc.sample_id;
