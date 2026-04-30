-- Advanced vendor parser audit queries for ObsidianDroid
-- Target DB: erebus_database_dev (MariaDB)
-- Purpose:
-- 1) Measure parser pressure points (generic/unknown/no-detection rates)
-- 2) Discover family token candidates from raw labels
-- 3) Build evidence for alias mapping (raw vendor token -> canonical family)
-- 4) Reduce future hardcoding by deriving rules from data distribution

USE erebus_database_dev;

-- ---------------------------------------------------------------------------
-- Common CTE: long-form vendor label table for the core ObsidianDroid parser set
-- ---------------------------------------------------------------------------
-- Core columns:
-- - sample_id
-- - vendor_name
-- - raw_label
-- - label_lc (lower/trimmed)
-- - normalized separator version: dot_label
WITH vendor_long AS (
    SELECT sample_id, 'ahnlab_v3' AS vendor_name, ahnlab_v3 AS raw_label
    FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'alibaba', alibaba FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'avast', avast FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'avast_mobile', avast_mobile FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'bitdefender', bitdefender FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'bitdefenderfalx', bitdefenderfalx FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'ikarus', ikarus FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'k7gw', k7gw FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'kaspersky', kaspersky FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'lionic', lionic FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'microsoft', microsoft FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'tencent', tencent FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'zonealarm', zonealarm FROM virustotal_sample_vendor_engine_verdicts
),
vendor_clean AS (
    SELECT
        vl.sample_id,
        vl.vendor_name,
        vl.raw_label,
        LOWER(TRIM(COALESCE(vl.raw_label, ''))) AS label_lc,
        REPLACE(REPLACE(REPLACE(LOWER(TRIM(COALESCE(vl.raw_label, ''))), ':', '.'), '-', '.'), '/', '.') AS dot_label
    FROM vendor_long vl
),
android_samples AS (
    SELECT
        m.sample_id,
        m.sha256,
        LOWER(TRIM(m.family_label)) AS family_label_lc,
        m.platform,
        m.file_extension,
        COALESCE(f.family_name, '') AS family_canonical,
        COALESCE(t.type_slug, '') AS type_slug
    FROM malware_sample_catalog m
    LEFT JOIN android_malware_family f
        ON LOWER(TRIM(m.family_label)) = LOWER(TRIM(f.family_name))
       AND f.is_active = 1
    LEFT JOIN android_malware_type t
        ON t.type_id = f.primary_type_id
    WHERE m.platform = 'android'
      AND m.file_extension = 'apk'
)
SELECT 1;

-- ---------------------------------------------------------------------------
-- Q1: Parser pressure summary by vendor (coverage + noisy label rates)
-- ---------------------------------------------------------------------------
WITH vendor_long AS (
    SELECT sample_id, 'ahnlab_v3' AS vendor_name, ahnlab_v3 AS raw_label
    FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'alibaba', alibaba FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'avast', avast FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'avast_mobile', avast_mobile FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'bitdefender', bitdefender FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'bitdefenderfalx', bitdefenderfalx FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'ikarus', ikarus FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'k7gw', k7gw FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'kaspersky', kaspersky FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'lionic', lionic FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'microsoft', microsoft FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'tencent', tencent FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'zonealarm', zonealarm FROM virustotal_sample_vendor_engine_verdicts
),
vendor_clean AS (
    SELECT
        vl.vendor_name,
        vl.sample_id,
        LOWER(TRIM(COALESCE(vl.raw_label, ''))) AS label_lc
    FROM vendor_long vl
)
SELECT
    vc.vendor_name,
    COUNT(*) AS n_total_rows,
    SUM(vc.label_lc <> '' AND vc.label_lc NOT IN ('none','null','n/a')) AS n_nonempty,
    ROUND(100 * SUM(vc.label_lc = '' OR vc.label_lc IN ('none','null','n/a')) / COUNT(*), 2) AS empty_pct,
    ROUND(100 * SUM(vc.label_lc IN ('undetected','type-unsupported','timeout','failure')) / COUNT(*), 2) AS no_detection_pct,
    ROUND(100 * SUM(vc.label_lc REGEXP 'unknown|generic|agent|malware') / COUNT(*), 2) AS genericish_pct,
    ROUND(100 * SUM(vc.label_lc REGEXP '(^|[^a-z])rat([^a-z]|$)|androrat|realrat|xrat|gravityrat|remote[- ]access') / COUNT(*), 2) AS rat_like_pct
FROM vendor_clean vc
GROUP BY vc.vendor_name
ORDER BY genericish_pct DESC, no_detection_pct DESC, vc.vendor_name;

-- ---------------------------------------------------------------------------
-- Q2: Vendor token structure profile (dot-separated token counts)
-- ---------------------------------------------------------------------------
WITH vendor_long AS (
    SELECT sample_id, 'ahnlab_v3' AS vendor_name, ahnlab_v3 AS raw_label
    FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'alibaba', alibaba FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'avast', avast FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'avast_mobile', avast_mobile FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'bitdefender', bitdefender FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'bitdefenderfalx', bitdefenderfalx FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'ikarus', ikarus FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'k7gw', k7gw FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'kaspersky', kaspersky FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'lionic', lionic FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'microsoft', microsoft FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'tencent', tencent FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'zonealarm', zonealarm FROM virustotal_sample_vendor_engine_verdicts
),
vendor_clean AS (
    SELECT
        vendor_name,
        REPLACE(REPLACE(REPLACE(LOWER(TRIM(COALESCE(raw_label, ''))), ':', '.'), '-', '.'), '/', '.') AS dot_label
    FROM vendor_long
    WHERE raw_label IS NOT NULL
      AND TRIM(raw_label) <> ''
      AND LOWER(TRIM(raw_label)) NOT IN ('none','null','n/a')
)
SELECT
    vendor_name,
    COUNT(*) AS n_labels,
    ROUND(AVG(1 + LENGTH(dot_label) - LENGTH(REPLACE(dot_label, '.', ''))), 2) AS avg_token_count,
    SUM(dot_label REGEXP 'android|androidos|andr|apk') AS android_token_hits,
    SUM(dot_label REGEXP 'bank|spy|rat|drop|ransom|adware|stealer|sms') AS threat_token_hits
FROM vendor_clean
GROUP BY vendor_name
ORDER BY avg_token_count DESC, vendor_name;

-- ---------------------------------------------------------------------------
-- Q3: Candidate family token mining (3rd token heuristic) by vendor
-- ---------------------------------------------------------------------------
WITH vendor_long AS (
    SELECT sample_id, 'ahnlab_v3' AS vendor_name, ahnlab_v3 AS raw_label
    FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'alibaba', alibaba FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'avast', avast FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'avast_mobile', avast_mobile FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'bitdefender', bitdefender FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'bitdefenderfalx', bitdefenderfalx FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'ikarus', ikarus FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'k7gw', k7gw FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'kaspersky', kaspersky FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'lionic', lionic FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'microsoft', microsoft FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'tencent', tencent FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'zonealarm', zonealarm FROM virustotal_sample_vendor_engine_verdicts
),
vendor_clean AS (
    SELECT
        sample_id,
        vendor_name,
        REPLACE(REPLACE(REPLACE(LOWER(TRIM(COALESCE(raw_label, ''))), ':', '.'), '-', '.'), '/', '.') AS dot_label
    FROM vendor_long
    WHERE raw_label IS NOT NULL
      AND TRIM(raw_label) <> ''
      AND LOWER(TRIM(raw_label)) NOT IN ('none','null','n/a')
),
tokens AS (
    SELECT
        vendor_name,
        sample_id,
        SUBSTRING_INDEX(SUBSTRING_INDEX(dot_label, '.', 3), '.', -1) AS token3
    FROM vendor_clean
)
SELECT
    vendor_name,
    token3,
    COUNT(*) AS n
FROM tokens
WHERE token3 <> ''
  AND token3 NOT REGEXP '^[0-9]+$'
GROUP BY vendor_name, token3
HAVING COUNT(*) >= 5
ORDER BY vendor_name, n DESC, token3;

-- ---------------------------------------------------------------------------
-- Q4: Data-driven alias evidence (vendor token -> canonical family)
-- ---------------------------------------------------------------------------
WITH vendor_long AS (
    SELECT sample_id, 'bitdefenderfalx' AS vendor_name, bitdefenderfalx AS raw_label
    FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'ikarus', ikarus FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'kaspersky', kaspersky FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'lionic', lionic FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'tencent', tencent FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'zonealarm', zonealarm FROM virustotal_sample_vendor_engine_verdicts
),
android_samples AS (
    SELECT
        m.sample_id,
        COALESCE(f.family_name, LOWER(TRIM(m.family_label))) AS family_canonical
    FROM malware_sample_catalog m
    LEFT JOIN android_malware_family f
        ON LOWER(TRIM(m.family_label)) = LOWER(TRIM(f.family_name))
       AND f.is_active = 1
    WHERE m.platform = 'android'
      AND m.file_extension = 'apk'
),
vendor_token AS (
    SELECT
        vl.vendor_name,
        vl.sample_id,
        SUBSTRING_INDEX(
            SUBSTRING_INDEX(
                REPLACE(REPLACE(REPLACE(LOWER(TRIM(COALESCE(vl.raw_label, ''))), ':', '.'), '-', '.'), '/', '.'),
                '.',
                3
            ),
            '.',
            -1
        ) AS vendor_family_token
    FROM vendor_long vl
    WHERE vl.raw_label IS NOT NULL
      AND TRIM(vl.raw_label) <> ''
      AND LOWER(TRIM(vl.raw_label)) NOT IN ('none','null','n/a','undetected','type-unsupported','timeout','failure')
)
SELECT
    vt.vendor_name,
    vt.vendor_family_token,
    a.family_canonical,
    COUNT(*) AS support
FROM vendor_token vt
JOIN android_samples a
  ON a.sample_id = vt.sample_id
WHERE vt.vendor_family_token <> ''
  AND vt.vendor_family_token NOT REGEXP '^[0-9]+$'
GROUP BY vt.vendor_name, vt.vendor_family_token, a.family_canonical
HAVING COUNT(*) >= 3
ORDER BY vt.vendor_name, support DESC, vt.vendor_family_token, a.family_canonical;

-- ---------------------------------------------------------------------------
-- Q5: Unmapped catalog families with strong vendor support (curation queue)
-- ---------------------------------------------------------------------------
WITH catalog AS (
    SELECT
        m.sample_id,
        LOWER(TRIM(m.family_label)) AS family_label_lc
    FROM malware_sample_catalog m
    WHERE m.platform = 'android'
      AND m.file_extension = 'apk'
),
mapped AS (
    SELECT LOWER(TRIM(family_name)) AS family_name_lc
    FROM android_malware_family
    WHERE is_active = 1
),
unmapped AS (
    SELECT c.sample_id, c.family_label_lc
    FROM catalog c
    LEFT JOIN mapped m
      ON m.family_name_lc = c.family_label_lc
    WHERE c.family_label_lc IS NOT NULL
      AND c.family_label_lc <> ''
      AND m.family_name_lc IS NULL
),
vendor_hits AS (
    SELECT
        u.family_label_lc,
        COUNT(*) AS n_samples,
        SUM(LOWER(COALESCE(v.kaspersky,'')) REGEXP u.family_label_lc) AS kaspersky_hits,
        SUM(LOWER(COALESCE(v.ikarus,'')) REGEXP u.family_label_lc) AS ikarus_hits,
        SUM(LOWER(COALESCE(v.tencent,'')) REGEXP u.family_label_lc) AS tencent_hits,
        SUM(LOWER(COALESCE(v.zonealarm,'')) REGEXP u.family_label_lc) AS zonealarm_hits
    FROM unmapped u
    JOIN virustotal_sample_vendor_engine_verdicts v
      ON v.sample_id = u.sample_id
    GROUP BY u.family_label_lc
)
SELECT
    family_label_lc,
    n_samples,
    kaspersky_hits,
    ikarus_hits,
    tencent_hits,
    zonealarm_hits,
    (kaspersky_hits + ikarus_hits + tencent_hits + zonealarm_hits) AS total_vendor_hits
FROM vendor_hits
ORDER BY total_vendor_hits DESC, n_samples DESC, family_label_lc
LIMIT 100;

-- ---------------------------------------------------------------------------
-- Q6: RAT/Remote semantic audit by vendor (for canonicalization checks)
-- ---------------------------------------------------------------------------
WITH vendor_long AS (
    SELECT sample_id, 'ahnlab_v3' AS vendor_name, ahnlab_v3 AS raw_label
    FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'alibaba', alibaba FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'avast', avast FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'avast_mobile', avast_mobile FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'bitdefender', bitdefender FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'bitdefenderfalx', bitdefenderfalx FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'ikarus', ikarus FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'k7gw', k7gw FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'kaspersky', kaspersky FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'lionic', lionic FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'microsoft', microsoft FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'tencent', tencent FROM virustotal_sample_vendor_engine_verdicts
    UNION ALL SELECT sample_id, 'zonealarm', zonealarm FROM virustotal_sample_vendor_engine_verdicts
)
SELECT
    vendor_name,
    COUNT(*) AS n_total,
    SUM(LOWER(COALESCE(raw_label,'')) REGEXP '(^|[^a-z])rat([^a-z]|$)|androrat|realrat|xrat|gravityrat') AS rat_hits,
    SUM(LOWER(COALESCE(raw_label,'')) REGEXP 'remote[- ]access|remote[_-]?admin|remoteaccess') AS remote_hits,
    SUM(LOWER(COALESCE(raw_label,'')) REGEXP 'spy') AS spy_hits
FROM vendor_long
WHERE raw_label IS NOT NULL
  AND TRIM(raw_label) <> ''
  AND LOWER(TRIM(raw_label)) NOT IN ('none','null','n/a')
GROUP BY vendor_name
ORDER BY rat_hits DESC, remote_hits DESC, spy_hits DESC;
