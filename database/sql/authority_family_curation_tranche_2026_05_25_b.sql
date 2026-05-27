-- Follow-on bounded live authority-family and alias curation tranche.
--
-- Scope:
--   - add a few remaining high-signal missing families
--   - add explicit alias rows for repeated conflict/composite tokens
--
-- Run with the target schema selected, for example:
--   mysql -u root -D erebus_threat_intel_prod < database/sql/authority_family_curation_tranche_2026_05_25_b.sql

SET NAMES utf8mb4;

START TRANSACTION;

-- ---------------------------------------------------------------------------
-- Add missing high-signal families.
-- ---------------------------------------------------------------------------
INSERT INTO android_malware_family (
    family_id, family_name, family_slug, primary_type_id, family_status,
    canonical_source_name, canonical_source_url, notes,
    review_reason, review_source_name, reviewed_at_utc, is_active
)
SELECT 94, 'MaliBot', 'malibot', 12, 'active',
       'The Hacker News', 'https://thehackernews.com/2022/06/malibot-new-android-banking-trojan.html',
       '2026-05-25: added from authority backlog pass.', 'authority_runtime_curation', 'operator_review', UTC_TIMESTAMP(), 1
WHERE NOT EXISTS (SELECT 1 FROM android_malware_family WHERE family_id = 94 OR family_slug = 'malibot');

INSERT INTO android_malware_family (
    family_id, family_name, family_slug, primary_type_id, family_status,
    canonical_source_name, canonical_source_url, notes,
    review_reason, review_source_name, reviewed_at_utc, is_active
)
SELECT 95, 'AgentSmith', 'agentsmith', 1, 'active',
       'Check Point', 'https://research.checkpoint.com/2019/agent-smith-a-new-species-of-mobile-malware/',
       '2026-05-25: added from authority backlog pass.', 'authority_runtime_curation', 'operator_review', UTC_TIMESTAMP(), 1
WHERE NOT EXISTS (SELECT 1 FROM android_malware_family WHERE family_id = 95 OR family_slug = 'agentsmith');

INSERT INTO android_malware_family (
    family_id, family_name, family_slug, primary_type_id, family_status,
    canonical_source_name, canonical_source_url, notes,
    review_reason, review_source_name, reviewed_at_utc, is_active
)
SELECT 96, 'xHelper', 'xhelper', 1, 'active',
       'Tech Advisor', 'https://www.techadvisor.com/article/737863/xhelper-android-malware-is-still-infecting-phones-and-is-unkillable.html',
       '2026-05-25: added from authority backlog pass.', 'authority_runtime_curation', 'operator_review', UTC_TIMESTAMP(), 1
WHERE NOT EXISTS (SELECT 1 FROM android_malware_family WHERE family_id = 96 OR family_slug = 'xhelper');

-- ---------------------------------------------------------------------------
-- Add explicit aliases to the legacy alias taxonomy used by live resolution.
-- ---------------------------------------------------------------------------
INSERT INTO android_malware_family_alias (
    alias_id, alias_name, alias_type, trust_tier, review_status,
    source_name, source_url, confidence, is_preferred, normalization_method,
    notes, family_id, is_active, created_at_utc, updated_at_utc
)
SELECT
    38, 'bankurt', 'public_report_name', 'curated_alias', 'accepted',
    'PCrisk', 'https://www.pcrisk.com/removal-guides/33985-klopatra-banking-trojan-android',
    0.950, 0, 'lower_trim_exact',
    '2026-05-25: curated alias for Klopatra from authority conflict backlog.',
    49, 1, UTC_TIMESTAMP(), UTC_TIMESTAMP()
WHERE NOT EXISTS (
    SELECT 1 FROM android_malware_family_alias WHERE LOWER(alias_name) = 'bankurt' AND family_id = 49
);

INSERT INTO android_malware_family_alias (
    alias_id, alias_name, alias_type, trust_tier, review_status,
    source_name, source_url, confidence, is_preferred, normalization_method,
    notes, family_id, is_active, created_at_utc, updated_at_utc
)
SELECT
    39, 'jocker', 'vendor_label', 'curated_alias', 'accepted',
    'PCRisk', 'https://www.pcrisk.com/removal-guides/17620-joker-trojan-android',
    0.900, 0, 'lower_trim_exact',
    '2026-05-25: curated alias for Joker from vendor conflict backlog.',
    46, 1, UTC_TIMESTAMP(), UTC_TIMESTAMP()
WHERE NOT EXISTS (
    SELECT 1 FROM android_malware_family_alias WHERE LOWER(alias_name) = 'jocker' AND family_id = 46
);

INSERT INTO android_malware_family_alias (
    alias_id, alias_name, alias_type, trust_tier, review_status,
    source_name, source_url, confidence, is_preferred, normalization_method,
    notes, family_id, is_active, created_at_utc, updated_at_utc
)
SELECT
    40, 'exobotcompact.d/octo', 'variant_label', 'contextual_variant', 'accepted',
    'operator_review', NULL,
    0.850, 0, 'lower_trim_exact',
    '2026-05-25: curated composite alias to Octo from resolved-family backlog.',
    34, 1, UTC_TIMESTAMP(), UTC_TIMESTAMP()
WHERE NOT EXISTS (
    SELECT 1 FROM android_malware_family_alias WHERE LOWER(alias_name) = 'exobotcompact.d/octo' AND family_id = 34
);

-- ---------------------------------------------------------------------------
-- Mirror the same aliases into the new alias fact table used by authority tooling.
-- ---------------------------------------------------------------------------
INSERT INTO malware_family_alias_fact (
    alias_token, canonical_family_slug, alias_kind, source_system, source_reference,
    confidence_score, is_active, notes
)
SELECT 'bankurt', 'klopatra', 'family_alias', 'operator_review',
       'android_malware_family_alias.bankurt', 0.9500, 1,
       '2026-05-25: curated alias from authority conflict backlog.'
WHERE NOT EXISTS (
    SELECT 1 FROM malware_family_alias_fact
    WHERE alias_token = 'bankurt' AND canonical_family_slug = 'klopatra' AND is_active = 1
);

INSERT INTO malware_family_alias_fact (
    alias_token, canonical_family_slug, alias_kind, source_system, source_reference,
    confidence_score, is_active, notes
)
SELECT 'jocker', 'joker', 'family_alias', 'operator_review',
       'android_malware_family_alias.jocker', 0.9000, 1,
       '2026-05-25: curated alias from authority conflict backlog.'
WHERE NOT EXISTS (
    SELECT 1 FROM malware_family_alias_fact
    WHERE alias_token = 'jocker' AND canonical_family_slug = 'joker' AND is_active = 1
);

INSERT INTO malware_family_alias_fact (
    alias_token, canonical_family_slug, alias_kind, source_system, source_reference,
    confidence_score, is_active, notes
)
SELECT 'exobotcompact.d/octo', 'octo', 'family_alias', 'operator_review',
       'android_malware_family_alias.exobotcompact.d/octo', 0.8500, 1,
       '2026-05-25: curated composite alias from resolved-family backlog.'
WHERE NOT EXISTS (
    SELECT 1 FROM malware_family_alias_fact
    WHERE alias_token = 'exobotcompact.d/octo' AND canonical_family_slug = 'octo' AND is_active = 1
);

COMMIT;

SELECT family_slug, family_name, primary_type_id, is_active
FROM android_malware_family
WHERE family_slug IN ('malibot','agentsmith','xhelper')
ORDER BY family_slug;

SELECT alias_name, family_id, is_active
FROM android_malware_family_alias
WHERE alias_name IN ('bankurt','jocker','exobotcompact.d/octo')
ORDER BY alias_name;
