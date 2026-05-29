# VT False-Positive Suppression Contract Gap

Date: `2026-05-26`

This note isolates the remaining QA gap after migrating live consumers to the
suppression-aware review view.

## What is fixed

- Quasar VT confidence readers now prefer
  `v_vt_false_positive_review_candidates_effective`.
- Erebus API/status readers now prefer
  `v_vt_false_positive_review_candidates_effective`.
- The effective view now enforces:
  - `active_flag = 1`
  - `starts_at_utc <= now` when present
  - `expires_at_utc > now` when present

## What is still intentionally not implemented

The suppression-rule table supports these scopes:

- `sample`
- `package`
- `label_pattern`
- `vendor`
- `family`
- `global`

The effective review view only operationalizes:

- `sample`
- `package`
- `label_pattern`
- `family`

That is deliberate for now.

## Why `global` is risky to auto-apply

Current active `global` rules are:

- `vt_malicious_count=1`
- `vt_malicious_count<=2 AND vt_harmless_count>=20`

If interpreted literally as suppression predicates over the live false-positive
review view, they would suppress most or all of the remaining review queue,
including genuine low-consensus malware-family rows such as `Gigabud`.

Live QA check:

- live review rows: `90`
- rows with `vt_malicious_count = 1`: `62`
- rows with `vt_malicious_count <= 2 AND vt_harmless_count >= 20`: `0`
- effective review rows: `52`
- effective rows with `vt_malicious_count = 1`: `36`

So literal execution of the first global rule would erase the majority of the
current analyst-visible surface. That is not a safe QA fix.

## Recommended contract

Treat the remaining unsupported scopes as explicit governance debt:

- `global`
  - likely query-definition or policy-guidance scope
  - not safe for direct SQL-string execution inside a view
- `vendor`
  - requires vendor identity columns on the review surface

## Next safe step

If these scopes are meant to be operational:

1. define exact typed semantics for each scope
2. add dedicated columns or joins required by those semantics
3. implement them in a new versioned query surface
4. avoid generic SQL-string evaluation from `scope_value`

The rerunnable SQL audit is:

- [database/sql/vt_false_positive_suppression_contract_gap_audit.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/vt_false_positive_suppression_contract_gap_audit.sql)
