# VT False-Positive Review Effective View

This view closes the main QA gap found in suppression review:

- `v_vt_false_positive_review_candidates` is suppression-unaware
- `v_vt_false_positive_review_candidates_effective` is suppression-aware

## Purpose

Use the new companion view when you want the operational review queue after
applying:

- `sample` suppressions
- `package` suppressions
- `label_pattern` suppressions
- `family` suppressions

The original view remains unchanged for compatibility and auditing.

## Expected Effect

At the time of creation:

- live view rows: `90`
- suppression-aware rows: `52`
- rows removed by suppression policy: `38`

## SQL

Use:

- [create_vt_false_positive_review_candidates_effective.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/create_vt_false_positive_review_candidates_effective.sql)
