/*
Backfill blank Android classification_subtype values only when sibling rows
for the same family_label already agree on exactly one nonblank subtype.

Conservative scope:
- platform = 'android'
- family_label present
- classification_subtype blank
- family has exactly one distinct nonblank subtype across Android rows
- excludes the generic 'unknown' family bucket
*/

UPDATE malware_sample_catalog AS msc
JOIN (
    SELECT
        LOWER(TRIM(family_label)) AS family_label_norm,
        MIN(NULLIF(TRIM(classification_subtype), '')) AS sole_subtype
    FROM malware_sample_catalog
    WHERE platform = 'android'
      AND COALESCE(TRIM(family_label), '') <> ''
    GROUP BY LOWER(TRIM(family_label))
    HAVING COUNT(DISTINCT NULLIF(TRIM(classification_subtype), '')) = 1
       AND family_label_norm <> 'unknown'
) AS fam
  ON fam.family_label_norm = LOWER(TRIM(msc.family_label))
SET msc.classification_subtype = fam.sole_subtype
WHERE msc.platform = 'android'
  AND COALESCE(TRIM(msc.family_label), '') <> ''
  AND COALESCE(TRIM(msc.classification_subtype), '') = '';
