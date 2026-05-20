-- Smoke checks for v_android_sample_family_type_authority.
--
-- Run after applying `view_android_sample_family_type_authority.sql`.

SET NAMES utf8mb4;

SELECT authority_bucket, COUNT(*) AS row_count
FROM v_android_sample_family_type_authority
GROUP BY authority_bucket
ORDER BY row_count DESC, authority_bucket ASC;

SELECT raw_vs_authority_status, COUNT(*) AS row_count
FROM v_android_sample_family_type_authority
GROUP BY raw_vs_authority_status
ORDER BY row_count DESC, raw_vs_authority_status ASC;

SELECT
    YEAR(vt_first_submission_at_utc) AS sample_year,
    authority_bucket,
    COUNT(*) AS row_count
FROM v_android_sample_family_type_authority
GROUP BY YEAR(vt_first_submission_at_utc), authority_bucket
ORDER BY sample_year ASC, authority_bucket ASC;

SELECT
    resolved_family_lc,
    authority_gap_reason,
    COUNT(*) AS row_count
FROM v_android_sample_family_type_authority
WHERE authority_bucket IN ('resolved_but_no_authority_family', 'generic_label_candidate')
GROUP BY resolved_family_lc, authority_gap_reason
ORDER BY row_count DESC, resolved_family_lc ASC
LIMIT 100;
