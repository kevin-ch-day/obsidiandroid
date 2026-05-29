-- Suppression-aware companion view for VT false-positive review.
-- This is intentionally additive: it leaves the current live view unchanged
-- while exposing the operationally correct review surface after applying
-- sample/package/label suppressions.
--
-- Important:
-- - This view enforces active_flag and rule time windows.
-- - It intentionally does NOT attempt to execute generic 'global' or
--   'vendor' scope expressions, because those scopes need a governed query
--   contract rather than ad-hoc SQL-string evaluation.
-- - ``family`` scope is safe to honor here because the review candidate view
--   already exposes a normalized family label for direct matching.

CREATE OR REPLACE VIEW v_vt_false_positive_review_candidates_effective AS
SELECT
  v.*
FROM v_vt_false_positive_review_candidates v
WHERE NOT EXISTS (
  SELECT 1
  FROM vt_false_positive_suppression_rule s
  WHERE s.active_flag = 1
    AND (s.starts_at_utc IS NULL OR s.starts_at_utc <= UTC_TIMESTAMP())
    AND (s.expires_at_utc IS NULL OR s.expires_at_utc > UTC_TIMESTAMP())
    AND (
      (s.scope_type = 'sample' AND s.scope_value = CAST(v.sample_id AS CHAR))
      OR (s.scope_type = 'package' AND s.scope_value = v.android_package_name)
      OR (s.scope_type = 'label_pattern' AND s.scope_value = v.sample_label)
      OR (
        s.scope_type = 'family'
        AND LOWER(TRIM(s.scope_value)) = LOWER(TRIM(COALESCE(v.family_label, '')))
      )
    )
);
