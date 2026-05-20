# Label Authority Schema Plan

This document defines the first safe schema layer for improving malware family and
type label authority in the ObsidianDroid platform.

The immediate problem is not model failure. It is that multiple label concepts are
currently easy to conflate:

- governed cohort truth (`family_id`, `family_canonical`, `type_slug`)
- raw catalog text (`family_label_raw`, `classification_primary`, `classification_subtype`)
- AV/vendor-derived label evidence
- model predictions
- rendered presentation labels (`classification_label`)

The goal of this plan is to make those roles explicit in data storage before any
future training-time label cleaning or label-noise mitigation.

## Current Safe Path (2026-05)

The immediate safe step is **not** the larger label-authority foundation pack.
The current live Erebus schema already has the beginnings of the right authority
model:

- `malware_sample_catalog`
- `android_malware_family`
- `android_malware_family_alias`
- `android_malware_type`
- `v_android_apk_family_norm`
- `v_android_apk_family_resolved`

The main current gap is that this authority is **partial and thin**, and
ObsidianDroid still has to reconstruct parts of the family/type story
downstream. The first production-safe move is therefore:

1. apply the read-only view
   - `database/sql/view_android_sample_family_type_authority.sql`
2. validate it with
   - `database/sql/view_android_sample_family_type_authority_smoke.sql`
3. use the non-invasive coverage report
   - `scripts/diagnostics/report_family_type_authority_coverage.py`
4. only then start consuming that view in ObsidianDroid diagnostics/readiness

The broader foundation scripts remain useful, but they are **future schema
work**, not the first deployment step.

## Design Principles

- **Authority is not evidence.**
  - Governed family/type truth must be stored separately from vendor-derived labels.
- **Evidence is not presentation.**
  - Rendered label strings should never be the only source for family/type claims.
- **ObsidianDroid should consume resolved authority, not invent it ad hoc.**
  - Erebus should own sample/family/type authority and vendor-label evidence layers.
- **Permission Intel stays separate.**
  - Permission Intel is not the owner of family/type truth.
- **ScytaleDroid owns APK-derived clustering and lineage facts.**
  - Signer/package-lineage support belongs there, then can be replicated into Erebus.

## Recommended Ownership

### Erebus

Recommended persisted tables:

- `malware_family_alias_fact`
- `malware_family_authority_fact`
- `malware_family_label_evidence`
- `vendor_label_generic_token_fact`
- `av_engine_dependency_fact`

Recommended read-only views:

- `v_android_sample_temporal_resolved`
- `label_authority_resolution_view`

### Permission Intel

No family/type authority objects should move here. Permission Intel should remain
focused on permission observations, dictionaries, and capability/behavior mappings.

### ScytaleDroid

Recommended future persisted tables:

- `sample_signer_cluster_fact`
- `sample_package_lineage_fact`

These are not part of the first authority-layer DDL in this pass, but they are the
right long-term owner for lineage evidence used by label-noise audits.

### ObsidianDroid

ObsidianDroid should consume:

- resolved authority views from Erebus
- permission views from Permission Intel
- lineage facts from ScytaleDroid

It should produce:

- run-scoped label-authority diagnostics
- label-noise candidate reports
- sensitivity evaluations

It should **not** become the source of truth for sample family/type authority.

## First Foundation Objects

### `malware_family_alias_fact`

Purpose:

- move family alias handling out of code-only constants
- version family alias governance
- track source and confidence

### `malware_family_authority_fact`

Purpose:

- make sample-level governed family/type assignment explicit
- preserve provenance for manual or automated authority resolution

### `malware_family_label_evidence`

Purpose:

- store normalized per-vendor label evidence separately from authority
- support AV agreement, generic-label, and drift diagnostics

### `vendor_label_generic_token_fact`

Purpose:

- normalize generic and class-like label tokens
- distinguish family labels from weak generic tags like `trojan`, `generic`,
  `downloader`, `basdoor`

### `av_engine_dependency_fact`

Purpose:

- annotate known or inferred dependencies between engines so AV agreement can be
  interpreted more carefully

### `v_android_sample_temporal_resolved`

Purpose:

- standardize the temporal anchor used by evaluation
- document whether `effective_first_seen_at_utc` came from
  `vt_first_seen_itw_date` or fallback `vt_first_submission_at_utc`

### `label_authority_resolution_view`

Purpose:

- provide one downstream projection that clearly separates:
  - raw catalog text
  - resolved catalog family slug
  - governed family/type authority
  - temporal anchor provenance
  - whether an explicit authority override exists

## Rollout Sequence

### Current production-safe sequence

1. Apply `v_android_sample_family_type_authority` in Erebus.
2. Run `view_android_sample_family_type_authority_smoke.sql`.
3. Run `report_family_type_authority_coverage.py` and confirm `Source mode: live_view`.
4. Switch ObsidianDroid **diagnostics/readiness** to consume the view.
5. Keep training behavior and family/type truth unchanged.

### Deferred foundation sequence

Only after the view is stable and downstream consumers are aligned:

1. Apply the larger schema foundation in Erebus.
2. Backfill `malware_family_alias_fact` from current code/constants plus analyst review.
3. Backfill `malware_family_authority_fact` from the current resolved family process.
4. Populate `malware_family_label_evidence` from VT/parsed vendor outputs.
5. Switch future label-authority/noise audits to richer evidence tables and views.
6. Only after that, add label-noise candidate scoring and sensitivity experiments.

## Deployment Helpers In This Repository

### Current safe objects

- `database/sql/view_android_sample_family_type_authority.sql`
  - proposed read-only authority projection over existing Erebus family/type objects
- `database/sql/view_android_sample_family_type_authority_smoke.sql`
  - smoke checks for authority buckets and raw-vs-authority status counts
- `scripts/diagnostics/report_family_type_authority_coverage.py`
  - non-invasive authority coverage report; uses the deployed view when present and embedded SQL fallback otherwise

### Deferred foundation objects

- `database/sql/label_authority_foundation.sql`
  - additive DDL for the first authority-layer tables and views
- `database/sql/label_authority_backfill.sql`
  - safe bootstrap for aliases and sample-level governed authority
- `database/sql/label_authority_vendor_evidence_backfill.sql`
  - first-pass seed from the wide VT verdict table into normalized vendor-label evidence
- `database/sql/label_authority_reference_seed.sql`
  - initial generic/class-like token policy for `vendor_label_generic_token_fact`
- `database/sql/label_authority_vendor_evidence_load_template.sql`
  - staging-first template for loading parser-enriched vendor evidence CSV
- `database/sql/label_authority_audit.sql`
  - SQL checks for authority conflicts, generic-label dominance, temporal gaps, and AV disagreement
- `database/sql/label_authority_schema_smoke.sql`
  - post-apply smoke checks
- `scripts/diagnostics/label_authority_schema_readiness.py`
  - pre-apply read-only readiness audit against a live Erebus instance
- `scripts/diagnostics/export_label_authority_vendor_evidence.py`
  - parser-enriched review/export file aligned to `malware_family_label_evidence`
- `scripts/diagnostics/summarize_label_authority_vendor_evidence.py`
  - markdown summary + alias-review candidate export from parser-enriched evidence
- `scripts/diagnostics/report_label_noise_candidates.py`
  - read-only sample-level label-risk scoring from vendor evidence + current authority
- `docs/LABEL_AUTHORITY_ROLLOUT_RUNBOOK.md`
  - intended staging-first apply order and review checklist

## What This Solves

- ambiguous meaning of `family_name` vs `family_canonical`
- blind use of vendor-derived family/type strings
- inability to audit authority provenance at sample level
- lack of explicit temporal anchor provenance
- lack of a clean place to store generic-label and AV-agreement metadata

## What This Does Not Do Yet

- no automatic relabeling
- no Confident Learning integration
- no training-time exclusion of noisy labels
- no change to current ObsidianDroid model behavior
- no collapse of Erebus, Permission Intel, and ScytaleDroid responsibilities
- no requirement to apply the larger `label_authority_*` schema pack before the
  read-only authority view is in use
