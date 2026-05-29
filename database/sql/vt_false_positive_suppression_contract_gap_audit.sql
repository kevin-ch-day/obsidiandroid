-- Contract-gap audit for suppression rules versus the operationally consumed
-- false-positive review view.

-- 1. Active rule inventory by scope type.
SELECT
  scope_type,
  COUNT(*) AS active_rules
FROM vt_false_positive_suppression_rule
WHERE active_flag = 1
GROUP BY scope_type
ORDER BY active_rules DESC, scope_type;

-- 2. Unsupported active scopes for the current effective view contract.
SELECT
  rule_id,
  rule_name,
  scope_type,
  scope_value,
  reason_code,
  starts_at_utc,
  expires_at_utc
FROM vt_false_positive_suppression_rule
WHERE active_flag = 1
  AND scope_type IN ('global', 'vendor')
ORDER BY scope_type, rule_id;

-- 3. Time-window rules and whether they are currently live.
SELECT
  rule_id,
  rule_name,
  scope_type,
  scope_value,
  reason_code,
  starts_at_utc,
  expires_at_utc,
  CASE
    WHEN starts_at_utc IS NOT NULL AND starts_at_utc > UTC_TIMESTAMP() THEN 'future'
    WHEN expires_at_utc IS NOT NULL AND expires_at_utc <= UTC_TIMESTAMP() THEN 'expired'
    ELSE 'active_window'
  END AS window_status
FROM vt_false_positive_suppression_rule
WHERE active_flag = 1
  AND (starts_at_utc IS NOT NULL OR expires_at_utc IS NOT NULL)
ORDER BY rule_id;

-- 4. Rules that are implemented by the effective view and match current rows.
SELECT
  r.rule_id,
  r.rule_name,
  r.scope_type,
  r.scope_value,
  r.reason_code,
  COUNT(v.sample_id) AS matched_live_rows
FROM vt_false_positive_suppression_rule r
LEFT JOIN v_vt_false_positive_review_candidates v
  ON (
    (r.scope_type = 'sample' AND r.scope_value = CAST(v.sample_id AS CHAR))
    OR (r.scope_type = 'package' AND r.scope_value = COALESCE(v.android_package_name, ''))
    OR (r.scope_type = 'label_pattern' AND r.scope_value = v.sample_label)
    OR (r.scope_type = 'family' AND LOWER(TRIM(r.scope_value)) = LOWER(TRIM(COALESCE(v.sample_label, ''))))
  )
WHERE r.active_flag = 1
  AND (r.starts_at_utc IS NULL OR r.starts_at_utc <= UTC_TIMESTAMP())
  AND (r.expires_at_utc IS NULL OR r.expires_at_utc > UTC_TIMESTAMP())
  AND r.scope_type IN ('sample', 'package', 'label_pattern', 'family')
GROUP BY r.rule_id, r.rule_name, r.scope_type, r.scope_value, r.reason_code
ORDER BY matched_live_rows DESC, r.rule_id;

-- 5. High-risk reminder: do not auto-execute current global rules as suppressions.
SELECT
  rule_id,
  rule_name,
  scope_value,
  reason_code
FROM vt_false_positive_suppression_rule
WHERE active_flag = 1
  AND scope_type = 'global'
ORDER BY rule_id;
