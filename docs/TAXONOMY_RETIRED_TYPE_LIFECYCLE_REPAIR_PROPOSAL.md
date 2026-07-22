# Taxonomy lifecycle repair proposal (read-only)

**Status:** proposal only — no taxonomy table updates, no family remaps, no type
reactivations applied.

**Evidence export:** `output/diagnostics/taxonomy_active_family_inactive_type_gaps_latest.csv`  
**Generator:** `scripts/diagnostics/report_taxonomy_type_lifecycle_gaps.py`  
**Corpus context run (archived, not modified):** `20260721T142432Z__07f657`
(under `output/runs/_archived/completed/allcurrent_diagnostic/`; live slot is
`20260721T231415Z__e0c43b`)
(`output/runs/allcurrent_diagnostic`; this superseded the older slot run
`20260721T014651Z__61b4a7`, which is no longer present).

## Related backlog snapshot (read-only regenerations; not committed)

Local ignored exports under `output/diagnostics/` were refreshed in the same
cleanup pass. They are **not** Git artifacts. Approximate live queue sizes at
refresh time:

| Export | Rows | Notes |
|--------|-----:|-------|
| `missing_primary_label_triage_latest.csv` | 6,196 | Schema includes `authority_family_is_active` / `authority_type_is_active` (`schema_status=compatible`) |
| `android_missing_resolution_triage_latest.csv` | 165 | Android missing-resolution worklist |
| `taxonomy_active_family_inactive_type_gaps_latest.csv` | 2 | Active family → retired type gaps below |

Regenerate with:

- `python scripts/diagnostics/report_missing_primary_label_triage.py`
- `python scripts/diagnostics/report_android_missing_resolution_triage.py`
- `python scripts/diagnostics/report_taxonomy_type_lifecycle_gaps.py`

## Gaps (active family → inactive/retired type)

| family_id | family_slug | family_status | primary_type_id | type_slug | authority_sample_count |
|-----------|-------------|---------------|-----------------|-----------|------------------------|
| 80 | kuguo | active | 19 | pua | 670 |
| 85 | smsworm | active | 10 | worm | 8 |

Total authority-linked samples affected: **678**.

## Why this matters

Prepared-cohort type accounting treats `pua` and `worm` as observed
`type_slug` values when samples resolve through these families. If the governed
type rows are inactive/retired while the families remain active, operators see:

- active family identities in family counts;
- type_slug labels that taxonomy governance considers retired;
- backlog lanes that route some missing-primary rows into
  `authority_retired_taxonomy_lifecycle_review`.

This pass does **not** change those records. It only documents the repair
choices for a later, explicitly authorized taxonomy curation session.

## Recommended repair options (choose per gap)

### Option A — Remap family primary type (preferred when a live successor exists)

1. Identify an **active** successor type that matches current research usage
   (for example adware/trojan/riskware for PUA-like adware droppers; trojan or
   sms-trojan for SMS worm-like families — exact successor must be confirmed
   against live `android_malware_type` rows and curator judgment).
2. Update `android_malware_family.primary_type_id` for the active family only.
3. Re-run read-only lifecycle gap export and confirm zero rows.
4. Recompute offline type-permission / cohort foundation summaries from a
   **new** run or offline snapshot refresh — do not rewrite the preserved run.

### Option B — Reactivate the retired type (only with curator evidence)

1. Document why `pua` / `worm` remain scientifically useful as governed types.
2. Set the type row active with an explicit audit note / change ticket.
3. Confirm family mappings still point at the reactivated type.
4. Re-export lifecycle gaps (expect empty).

### Option C — Deactivate or retire the family (only if samples should leave authority)

1. Use when the family should no longer be an active authority identity.
2. Requires sample remapping / backlog handling for the authority-linked rows
   (670 for kuguo, 8 for smsworm).
3. Higher risk for live-corpus continuity; prefer A or B unless curators agree
   the family identity itself is obsolete.

## Explicit non-actions for this pass

- No `UPDATE` / `INSERT` / `DELETE` on taxonomy tables.
- No Core writes; no grant/migration changes.
- No modification of archived run `20260721T142432Z__07f657` evidence.
- No automatic “fix” from this proposal document.

## Suggested follow-up ticket checklist

- [ ] Curator confirms successor type_slug for `kuguo` (or reactivation of `pua`).
- [ ] Curator confirms successor type_slug for `smsworm` (or reactivation of `worm`).
- [ ] Apply Option A or B in a dedicated taxonomy session with audit notes.
- [ ] Regenerate `taxonomy_active_family_inactive_type_gaps_latest.csv` (expect 0 rows).
- [ ] Regenerate missing-primary triage and confirm
      `authority_retired_taxonomy_lifecycle_review` shrinks appropriately.
- [ ] Optional: new diagnostic pipeline run after taxonomy change (separate from
      this cleanup pass).
