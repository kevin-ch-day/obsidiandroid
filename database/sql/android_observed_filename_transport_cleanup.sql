-- Conservative cleanup for obviously corrupted Android `observed_filename`
-- values. This only fixes transport / whitespace artifacts and does not try to
-- infer or replace true filenames.
--
-- Safe cleanup scope:
--   - trim leading / trailing whitespace
--   - replace literal escape fragments (\r, \n, \t) with spaces
--   - replace actual control characters with spaces
--   - collapse repeated whitespace
--   - convert now-empty results to NULL
--
-- Intentionally excluded:
--   - blanket removal of all non-ASCII characters
--   - heuristics that guess a filename from labels or source URLs
--
-- Run from the primary schema, for example:
--   mysql -t -D erebus_threat_intel_prod < database/sql/android_observed_filename_transport_cleanup.sql

SET NAMES utf8mb4;

-- Preview the number of rows eligible for this cleanup.
SELECT
    COUNT(*) AS pre_update_candidates
FROM malware_sample_catalog
WHERE LOWER(TRIM(COALESCE(platform, ''))) = 'android'
  AND observed_filename IS NOT NULL
  AND (
         observed_filename <> TRIM(observed_filename)
      OR observed_filename REGEXP '[[:cntrl:]]'
      OR observed_filename LIKE '%\\\\r%'
      OR observed_filename LIKE '%\\\\n%'
      OR observed_filename LIKE '%\\\\t%'
  );

UPDATE malware_sample_catalog
SET observed_filename = NULLIF(
    TRIM(
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                REPLACE(
                    REPLACE(
                        REPLACE(observed_filename, '\\r', ' '),
                        '\\n',
                        ' '
                    ),
                    '\\t',
                    ' '
                ),
                '[[:cntrl:]]+',
                ' '
            ),
            '[[:space:]]+',
            ' '
        )
    ),
    ''
)
WHERE LOWER(TRIM(COALESCE(platform, ''))) = 'android'
  AND observed_filename IS NOT NULL
  AND (
         observed_filename <> TRIM(observed_filename)
      OR observed_filename REGEXP '[[:cntrl:]]'
      OR observed_filename LIKE '%\\\\r%'
      OR observed_filename LIKE '%\\\\n%'
      OR observed_filename LIKE '%\\\\t%'
  );

SELECT ROW_COUNT() AS updated_rows;

SELECT
    COUNT(*) AS post_update_candidates
FROM malware_sample_catalog
WHERE LOWER(TRIM(COALESCE(platform, ''))) = 'android'
  AND observed_filename IS NOT NULL
  AND (
         observed_filename <> TRIM(observed_filename)
      OR observed_filename REGEXP '[[:cntrl:]]'
      OR observed_filename LIKE '%\\\\r%'
      OR observed_filename LIKE '%\\\\n%'
      OR observed_filename LIKE '%\\\\t%'
  );
