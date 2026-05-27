-- Live authority runtime patch for ObsidianDroid / Erebus-integrated catalogs.
--
-- Purpose:
--   1. Add alias activeness to the legacy alias taxonomy table.
--   2. Rebuild v_android_apk_family_resolved with active-only family/alias joins.
--   3. Apply the additive label-authority foundation objects.
--   4. Seed authority rows from the now-corrected resolved family view.
--   5. Rebuild v_android_sample_family_type_authority against active taxonomy rows.
--
-- Run with the target schema selected, for example:
--   mysql -u root -D erebus_threat_intel_prod < database/sql/label_authority_live_runtime_patch.sql

SET NAMES utf8mb4;

ALTER TABLE android_malware_family_alias
    ADD COLUMN IF NOT EXISTS is_active TINYINT(1) NOT NULL DEFAULT 1 AFTER family_id,
    ADD KEY IF NOT EXISTS idx_android_family_alias_alias_active (alias_name, is_active),
    ADD KEY IF NOT EXISTS idx_android_family_alias_family_active (family_id, is_active);

DROP VIEW IF EXISTS v_android_apk_family_resolved;
CREATE VIEW v_android_apk_family_resolved AS
SELECT
    n.sample_id AS sample_id,
    n.sha256 AS sha256,
    n.family_lc AS family_lc,
    LOWER(
        TRIM(
            COALESCE(
                fd.family_name,
                fr.family_name,
                n.family_lc
            )
        )
    ) AS resolved_family_lc
FROM v_android_apk_family_norm AS n
LEFT JOIN android_malware_family AS fd
    ON LOWER(TRIM(fd.family_name)) = n.family_lc
   AND fd.is_active = 1
LEFT JOIN android_malware_family_alias AS fa
    ON LOWER(TRIM(fa.alias_name)) = n.family_lc
   AND fa.is_active = 1
LEFT JOIN android_malware_family AS fr
    ON fr.family_id = fa.family_id
   AND fr.is_active = 1;

SOURCE database/sql/label_authority_foundation.sql;
SOURCE database/sql/label_authority_backfill.sql;
SOURCE database/sql/view_android_sample_family_type_authority.sql;
