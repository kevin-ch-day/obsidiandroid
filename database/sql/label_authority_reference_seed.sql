-- Label authority reference-data seed helpers.
--
-- Use this after `label_authority_foundation.sql` and before downstream
-- generic-label or AV-agreement diagnostics that depend on token policy.
--
-- Conventions:
--   - vendor_key='__global__' means a vendor-agnostic default policy
--   - later vendor-specific rows can coexist and override/extend this seed

SET NAMES utf8mb4;

INSERT INTO vendor_label_generic_token_fact (
    vendor_key,
    raw_token,
    normalized_token,
    token_kind,
    generic_default_flag,
    source_system,
    source_reference,
    is_active,
    notes
)
VALUES
    ('__global__', 'unknown', 'unknown', 'placeholder_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'global default placeholder token'),
    ('__global__', 'generic', 'generic', 'placeholder_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'global default placeholder token'),
    ('__global__', 'none', 'none', 'placeholder_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'global default placeholder token'),
    ('__global__', 'null', 'null', 'placeholder_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'global default placeholder token'),
    ('__global__', 'malware', 'malware', 'generic_family_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'generic family token, not a canonical family'),
    ('__global__', 'agent', 'agent', 'generic_family_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'generic family token, not a canonical family'),
    ('__global__', 'trojan', 'trojan', 'behavior_class_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'class-like token, not family authority'),
    ('__global__', 'downloader', 'downloader', 'behavior_class_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'class-like token, not family authority'),
    ('__global__', 'dropper', 'dropper', 'behavior_class_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'class-like token, not family authority'),
    ('__global__', 'stealer', 'stealer', 'behavior_class_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'class-like token, not family authority'),
    ('__global__', 'spyware', 'spyware', 'behavior_class_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'class-like token, not family authority'),
    ('__global__', 'adware', 'adware', 'behavior_class_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'class-like token, not family authority'),
    ('__global__', 'backdoor', 'backdoor', 'behavior_class_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'class-like token, not family authority'),
    ('__global__', 'riskware', 'riskware', 'behavior_class_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'class-like token, not family authority'),
    ('__global__', 'grayware', 'grayware', 'behavior_class_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'class-like token, not family authority'),
    ('__global__', 'pua', 'pua', 'behavior_class_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'class-like token, not family authority'),
    ('__global__', 'pup', 'pup', 'behavior_class_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'class-like token, not family authority'),
    ('__global__', 'heur', 'heur', 'heuristic_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'heuristic token, not family authority'),
    ('__global__', 'heuristic', 'heuristic', 'heuristic_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'heuristic token, not family authority'),
    ('__global__', 'notavirus', 'notavirus', 'heuristic_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'heuristic/grayware token, not family authority'),
    ('__global__', 'monitor', 'monitor', 'behavior_class_token', 1, 'erebus', 'label_authority_reference_seed.sql', 1, 'behavior token, not family authority')
ON DUPLICATE KEY UPDATE
    generic_default_flag = VALUES(generic_default_flag),
    source_reference = VALUES(source_reference),
    notes = VALUES(notes),
    updated_at_utc = CURRENT_TIMESTAMP;

-- Optional sanity snapshot.
SELECT
    vendor_key,
    token_kind,
    COUNT(*) AS token_count
FROM vendor_label_generic_token_fact
WHERE is_active = 1
GROUP BY vendor_key, token_kind
ORDER BY vendor_key ASC, token_kind ASC;
