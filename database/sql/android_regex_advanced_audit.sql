-- Advanced regex/morphology audit for residual authority debt and effective
-- false-positive review residue.

-- 1. Residual unresolved-family token morphology buckets.
WITH unresolved AS (
  SELECT LOWER(TRIM(COALESCE(resolved_family_lc, ''))) AS token
  FROM v_android_sample_family_type_authority
  WHERE authority_bucket = 'resolved_but_no_authority_family'
),
bucketed AS (
  SELECT
    token,
    CASE
      WHEN token = '' THEN 'blank'
      WHEN token REGEXP 'spy' THEN 'contains_spy'
      WHEN token REGEXP 'rat' THEN 'contains_rat'
      WHEN token REGEXP 'bot' THEN 'contains_bot'
      WHEN token REGEXP 'bank|loan' THEN 'contains_bank_or_loan'
      WHEN token REGEXP 'steal|thief' THEN 'contains_steal_or_thief'
      WHEN token REGEXP 'drop' THEN 'contains_drop'
      WHEN token REGEXP 'pack' THEN 'contains_pack'
      WHEN token REGEXP 'lock|ransom' THEN 'contains_lock_or_ransom'
      WHEN token REGEXP 'worm' THEN 'contains_worm'
      WHEN token REGEXP 'miner|crypto' THEN 'contains_crypto_or_miner'
      WHEN token REGEXP 'fraud|fake|phish' THEN 'contains_fake_fraud_phish'
      WHEN token REGEXP 'root' THEN 'contains_root'
      WHEN token REGEXP 'ad' THEN 'contains_ad'
      ELSE 'no_signal_stem'
    END AS stem_bucket
  FROM unresolved
)
SELECT
  stem_bucket,
  COUNT(*) AS row_count,
  GROUP_CONCAT(token ORDER BY token SEPARATOR ' | ') AS tokens
FROM bucketed
GROUP BY stem_bucket
ORDER BY row_count DESC, stem_bucket;

-- 2. Structural shape buckets for unresolved-family tokens.
WITH unresolved AS (
  SELECT LOWER(TRIM(COALESCE(resolved_family_lc, ''))) AS token
  FROM v_android_sample_family_type_authority
  WHERE authority_bucket = 'resolved_but_no_authority_family'
),
bucketed AS (
  SELECT
    token,
    CASE
      WHEN token = '' THEN 'blank'
      WHEN token REGEXP '^[a-z]+$' THEN 'letters_only'
      WHEN token REGEXP '^[a-z]+[0-9]+$|^[0-9]+[a-z]+$' THEN 'alnum_compact'
      WHEN token REGEXP '[[:space:]]' THEN 'contains_space'
      WHEN token REGEXP '[._-]' THEN 'contains_punct'
      ELSE 'other'
    END AS shape_bucket
  FROM unresolved
)
SELECT
  shape_bucket,
  COUNT(*) AS row_count,
  GROUP_CONCAT(token ORDER BY token SEPARATOR ' | ') AS tokens
FROM bucketed
GROUP BY shape_bucket
ORDER BY row_count DESC, shape_bucket;

-- 3. Missing-resolution package morphology paired with VT-tail presence.
WITH miss AS (
  SELECT
    c.sample_id AS sample_id,
    COALESCE(c.android_package_name, '') AS pkg,
    COALESCE(c.vt_family_token, '') AS vt_token,
    COALESCE(c.vt_suggested_label, '') AS vt_label
  FROM malware_sample_catalog c
  JOIN v_android_sample_family_type_authority a
    ON a.sample_id = c.sample_id
  WHERE a.authority_bucket = 'missing_resolved_family'
),
bucketed AS (
  SELECT
    sample_id,
    pkg,
    CASE
      WHEN pkg = '' THEN 'blank_package'
      WHEN LOWER(pkg) REGEXP '^com\\.[a-z0-9_]+\\.[a-z0-9_.]+$' THEN 'com_style_package'
      WHEN LOWER(pkg) REGEXP '^(net|org|io|de|by|app)\\.[a-z0-9_]+\\.[a-z0-9_.]+$' THEN 'other_tld_style_package'
      WHEN LOWER(pkg) REGEXP 'tencent|antivirus|wallet|apk|video|learn|driver' THEN 'semantic_package_keyword'
      ELSE 'other_package_shape'
    END AS pkg_bucket,
    CASE
      WHEN LOWER(vt_token) REGEXP 'jiagu|boogr|fklz' THEN 'weak_vt_tail_present'
      WHEN vt_token = '' AND vt_label = '' THEN 'no_vt_tail'
      ELSE 'other_vt_tail'
    END AS vt_tail_bucket
  FROM miss
)
SELECT
  pkg_bucket,
  vt_tail_bucket,
  COUNT(*) AS row_count,
  GROUP_CONCAT(
    CONCAT(sample_id, ':', COALESCE(NULLIF(pkg, ''), '<blank>'))
    ORDER BY sample_id
    SEPARATOR ' | '
  ) AS examples
FROM bucketed
GROUP BY pkg_bucket, vt_tail_bucket
ORDER BY row_count DESC, pkg_bucket, vt_tail_bucket;

-- 4. Effective false-positive review residue by label morphology.
WITH eff AS (
  SELECT
    COALESCE(sample_label, '') AS sample_label,
    platform
  FROM v_vt_false_positive_review_candidates_effective
),
parts AS (
  SELECT
    sample_label,
    platform,
    LOWER(sample_label) AS l,
    LENGTH(sample_label) AS label_len
  FROM eff
),
bucketed AS (
  SELECT
    sample_label,
    platform,
    label_len,
    CASE
      WHEN l REGEXP '^[a-f0-9]{8,}(\\.|$)' THEN 'hash_prefix_like'
      WHEN l REGEXP '\\.(exe|dll|apk|jar|zip|rar|doc|png|so|virus|file)$' THEN 'file_suffix_like'
      WHEN l REGEXP 'unknown|unclassified|phishing' THEN 'generic_placeholder'
      WHEN l REGEXP 'banker|trojan|adware' THEN 'generic_threat_class'
      WHEN l REGEXP 'setup|install|uninstall' THEN 'installer_family'
      WHEN l REGEXP '^[a-z][a-z0-9._-]{2,}$' THEN 'compact_slug'
      ELSE 'other'
    END AS shape_bucket
  FROM parts
)
SELECT
  shape_bucket,
  platform,
  COUNT(*) AS row_count,
  ROUND(AVG(label_len), 1) AS avg_len,
  GROUP_CONCAT(sample_label ORDER BY sample_label SEPARATOR ' | ') AS labels
FROM bucketed
GROUP BY shape_bucket, platform
ORDER BY row_count DESC, shape_bucket, platform;

-- 5. Effective FP compact slugs worth separate malware review, not suppression.
SELECT
  sample_label,
  platform,
  COUNT(*) AS row_count,
  MIN(vt_malicious_count) AS min_malicious,
  MAX(vt_malicious_count) AS max_malicious,
  GROUP_CONCAT(sample_id ORDER BY sample_id) AS sample_ids
FROM v_vt_false_positive_review_candidates_effective
WHERE LOWER(sample_label) REGEXP '^[a-z][a-z0-9._-]{2,}$'
GROUP BY sample_label, platform
ORDER BY row_count DESC, sample_label, platform;
