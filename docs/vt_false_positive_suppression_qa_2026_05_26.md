# VT False-Positive Suppression QA

## Main QA Finding

The table `vt_false_positive_suppression_rule` is being populated, but the live
view `v_vt_false_positive_review_candidates` does **not** currently reference it.

That means:

- suppression rules exist in the database
- but the main false-positive review surface is still suppression-unaware

## Evidence

`SHOW CREATE VIEW v_vt_false_positive_review_candidates` currently resolves to:

- `vt_sample_verdict_confidence_current`
- `malware_sample_catalog`

It does **not** join or filter on `vt_false_positive_suppression_rule`.

## Why This Matters

Without a suppression-aware review view or downstream consumer:

- package suppressions do not directly reduce the visible review queue
- exact-label suppressions do not directly reduce the visible review queue
- sample suppressions do not directly reduce the visible review queue

The rules are still useful as policy state, but they are not yet fully
operational.

## Safe Next Step

Use:

- [vt_false_positive_review_suppression_audit.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/vt_false_positive_review_suppression_audit.sql)

This provides:

1. raw live-view count
2. count of rows in the live view that already match suppression rules
3. suppression-aware candidate count
4. examples of rows that remain visible despite matching suppression policy

This keeps the QA step read-only and makes the wiring gap explicit before any
live view definition is changed.
