-- Bounded live authority-family curation tranche.
--
-- Scope:
--   - reactivate known families that already exist in android_malware_family
--   - assign concrete primary types where rows were left unknown
--   - add a small number of high-support missing families from the live
--     authority backlog
--
-- Run with the target schema selected, for example:
--   mysql -u root -D erebus_threat_intel_prod < database/sql/authority_family_curation_tranche_2026_05_25.sql

SET NAMES utf8mb4;

START TRANSACTION;

-- ---------------------------------------------------------------------------
-- Reactivate existing inactive families with concrete primary types.
-- ---------------------------------------------------------------------------
UPDATE android_malware_family
SET
    primary_type_id = 12,
    family_status = 'active',
    is_active = 1,
    canonical_source_name = 'Verimatrix',
    canonical_source_url = 'https://www.verimatrix.com/cybersecurity/cybersecurity-insights/copybara-android-banking-trojan-alert/',
    review_reason = 'authority_runtime_curation',
    review_source_name = 'operator_review',
    reviewed_at_utc = UTC_TIMESTAMP(),
    notes = CONCAT_WS('\n', NULLIF(notes, ''), '2026-05-25: reactivated and typed as banker from authority backlog pass.')
WHERE family_slug = 'copybara';

UPDATE android_malware_family
SET
    primary_type_id = 12,
    family_status = 'active',
    is_active = 1,
    canonical_source_name = 'DSCI',
    canonical_source_url = 'https://www.dsci.in/files/content/advisory/2025/Threat-Advisory-February-2025-v3.pdf',
    review_reason = 'authority_runtime_curation',
    review_source_name = 'operator_review',
    reviewed_at_utc = UTC_TIMESTAMP(),
    notes = CONCAT_WS('\n', NULLIF(notes, ''), '2026-05-25: reactivated and typed as banker from authority backlog pass.')
WHERE family_slug = 'fatboypanel';

UPDATE android_malware_family
SET
    primary_type_id = 2,
    family_status = 'active',
    is_active = 1,
    canonical_source_name = 'McAfee',
    canonical_source_url = 'https://www.mcafee.com/blogs/other-blogs/mcafee-labs/spyloan-a-global-threat-exploiting-social-engineering/',
    review_reason = 'authority_runtime_curation',
    review_source_name = 'operator_review',
    reviewed_at_utc = UTC_TIMESTAMP(),
    notes = CONCAT_WS('\n', NULLIF(notes, ''), '2026-05-25: reactivated and typed as spyware from authority backlog pass.')
WHERE family_slug = 'spyloan';

UPDATE android_malware_family
SET
    primary_type_id = 12,
    family_status = 'active',
    is_active = 1,
    canonical_source_name = 'AWAKE',
    canonical_source_url = 'https://awakewiki.org/malware/families/brata/',
    review_reason = 'authority_runtime_curation',
    review_source_name = 'operator_review',
    reviewed_at_utc = UTC_TIMESTAMP(),
    notes = CONCAT_WS('\n', NULLIF(notes, ''), '2026-05-25: reactivated as banking trojan family from authority backlog pass.')
WHERE family_slug = 'brata';

UPDATE android_malware_family
SET
    primary_type_id = 12,
    family_status = 'active',
    is_active = 1,
    canonical_source_name = 'Cyble',
    canonical_source_url = 'https://cybersecuritynews.com/android-banking-trojan-google-play-mimic/',
    review_reason = 'authority_runtime_curation',
    review_source_name = 'operator_review',
    reviewed_at_utc = UTC_TIMESTAMP(),
    notes = CONCAT_WS('\n', NULLIF(notes, ''), '2026-05-25: reactivated and typed as banker from authority backlog pass.')
WHERE family_slug = 'antidot';

UPDATE android_malware_family
SET
    primary_type_id = 3,
    family_status = 'active',
    is_active = 1,
    canonical_source_name = 'HUMAN Security',
    canonical_source_url = 'https://www.humansecurity.com/learn/blog/terracotta-android-malware-a-technical-study/',
    review_reason = 'authority_runtime_curation',
    review_source_name = 'operator_review',
    reviewed_at_utc = UTC_TIMESTAMP(),
    notes = CONCAT_WS('\n', NULLIF(notes, ''), '2026-05-25: reactivated and typed as adware from authority backlog pass.')
WHERE family_slug = 'terracotta';

UPDATE android_malware_family
SET
    primary_type_id = 12,
    family_status = 'active',
    is_active = 1,
    canonical_source_name = 'ThreatFabric',
    canonical_source_url = 'https://blog.polyswarm.io/brokewell-android-banking-trojan',
    review_reason = 'authority_runtime_curation',
    review_source_name = 'operator_review',
    reviewed_at_utc = UTC_TIMESTAMP(),
    notes = CONCAT_WS('\n', NULLIF(notes, ''), '2026-05-25: reactivated and typed as banker from authority backlog pass.')
WHERE family_slug = 'brokewell';

-- ---------------------------------------------------------------------------
-- Add missing high-support families from the live authority backlog.
-- ---------------------------------------------------------------------------
INSERT INTO android_malware_family (
    family_id,
    family_name,
    family_slug,
    primary_type_id,
    family_status,
    canonical_source_name,
    canonical_source_url,
    notes,
    review_reason,
    review_source_name,
    reviewed_at_utc,
    is_active
)
SELECT 89, 'IconHiding', 'iconhiding', 3, 'active',
       'Sophos', 'https://news.sophos.com/en-us/2019/10/08/icon-hiding-android-adware-returns-to-the-play-market/',
       '2026-05-25: added from authority backlog pass.', 'authority_runtime_curation', 'operator_review', UTC_TIMESTAMP(), 1
WHERE NOT EXISTS (SELECT 1 FROM android_malware_family WHERE family_id = 89 OR family_slug = 'iconhiding');

INSERT INTO android_malware_family (
    family_id, family_name, family_slug, primary_type_id, family_status,
    canonical_source_name, canonical_source_url, notes,
    review_reason, review_source_name, reviewed_at_utc, is_active
)
SELECT 90, 'RatOn', 'raton', 12, 'active',
       'ThreatFabric', 'https://www.techradar.com/pro/security/new-android-rat-uses-near-field-communication-to-automatically-steal-money-from-devices',
       '2026-05-25: added from authority backlog pass.', 'authority_runtime_curation', 'operator_review', UTC_TIMESTAMP(), 1
WHERE NOT EXISTS (SELECT 1 FROM android_malware_family WHERE family_id = 90 OR family_slug = 'raton');

INSERT INTO android_malware_family (
    family_id, family_name, family_slug, primary_type_id, family_status,
    canonical_source_name, canonical_source_url, notes,
    review_reason, review_source_name, reviewed_at_utc, is_active
)
SELECT 91, 'Herodotus', 'herodotus', 16, 'active',
       'PCrisk', 'https://www.pcrisk.com/removal-guides/34213-herodotus-malware-android',
       '2026-05-25: added from authority backlog pass.', 'authority_runtime_curation', 'operator_review', UTC_TIMESTAMP(), 1
WHERE NOT EXISTS (SELECT 1 FROM android_malware_family WHERE family_id = 91 OR family_slug = 'herodotus');

INSERT INTO android_malware_family (
    family_id, family_name, family_slug, primary_type_id, family_status,
    canonical_source_name, canonical_source_url, notes,
    review_reason, review_source_name, reviewed_at_utc, is_active
)
SELECT 92, 'PixBankBot', 'pixbankbot', 12, 'active',
       'Appdome', 'https://www.appdome.com/how-to//account-takeover-prevention/protect-android-apps-against-pixbankbot-malware/',
       '2026-05-25: added from authority backlog pass.', 'authority_runtime_curation', 'operator_review', UTC_TIMESTAMP(), 1
WHERE NOT EXISTS (SELECT 1 FROM android_malware_family WHERE family_id = 92 OR family_slug = 'pixbankbot');

INSERT INTO android_malware_family (
    family_id, family_name, family_slug, primary_type_id, family_status,
    canonical_source_name, canonical_source_url, notes,
    review_reason, review_source_name, reviewed_at_utc, is_active
)
SELECT 93, 'Scylla', 'scylla', 3, 'active',
       'The Hacker News', 'https://thehackernews.com/2022/09/experts-uncover-85-apps-with-13-million.html',
       '2026-05-25: added from authority backlog pass.', 'authority_runtime_curation', 'operator_review', UTC_TIMESTAMP(), 1
WHERE NOT EXISTS (SELECT 1 FROM android_malware_family WHERE family_id = 93 OR family_slug = 'scylla');

COMMIT;

SELECT family_slug, family_name, primary_type_id, is_active
FROM android_malware_family
WHERE family_slug IN (
    'copybara','fatboypanel','spyloan','brata','antidot','terracotta','brokewell',
    'iconhiding','raton','herodotus','pixbankbot','scylla'
)
ORDER BY family_slug;
