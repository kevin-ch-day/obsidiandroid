# ObsidianDroid Canonical Run Contract

The canonical-run contract defines the current Android malware-classification and
permission-pattern research boundary. It is **not** the later deep-learning
system and does **not** absorb ScytaleDroid responsibilities.

## Scope

The contract positions ObsidianDroid as a governed, reproducible platform for:

- authority-aware Android malware cohort selection
- family/type benchmark classification
- permission-feature research and permission-pattern reporting
- manifest-backed run observability, evidence, and diagnostics

The platform is intended to feed later Neptune / Iapetus work, not replace it.

## Database ownership boundary

ObsidianDroid stays **downstream** from upstream intelligence systems.

- **Erebus** remains the owner of Android sample catalog, VT-derived metadata, and
  family/type authority truth.
- **Permission Intel** remains the owner of live `android_permission_*` tables and
  permission-source governance metadata.
- **ObsidianDroid** may read from both systems and may persist its own
  run-scoped summaries, diagnostics, and research outputs in
  ObsidianDroid-owned tables.
- ObsidianDroid must **not** write back into Erebus source tables or mutate live
  Permission Intel source-of-truth tables.

This keeps the platform production-safe while still allowing later persistence and audit.

## Permission-pattern contract

The contract adopts a normalized **0–9 structural permission-pattern ladder** (association
strength, not malware proof or causality):

| Level | Label |
| ---: | --- |
| 0 | Null / Absent Pattern |
| 1 | Trace Pattern |
| 2 | Very Weak Pattern |
| 3 | Weak Pattern |
| 4 | Weak-Moderate Pattern |
| 5 | Moderate Pattern |
| 6 | Moderate-Strong Pattern |
| 7 | Strong Pattern |
| 8 | Very Strong Pattern |
| 9 | Certain Pattern |

Standalone contract artifacts: `permission_pattern_contract_{run_id}.json/.md`.

Existing permission-pattern outputs may now expose:

- `pattern_score`
- `pattern_level`
- `pattern_label`
- `pattern_basis`
- `pattern_confidence`
- `pattern_reason`

These fields normalize interpretation without replacing the underlying
prevalence/enrichment metrics.

## Inference mode vs rebuild mode

The contract treats these as design concepts even where the full inference-only path is not
yet a first-class CLI workflow.

- **Inference mode** means classifying newly added samples against a frozen
  baseline and frozen trained model without rebuilding the benchmark cohort.
- **Rebuild mode** means re-resolving the cohort, refreshing alignment, retraining,
  and emitting a new benchmark baseline.

canonical primarily implements rebuild mode plus locked-baseline reproducibility
controls. A dedicated frozen-model inference path is a follow-on capability.

## What moves to later release or later

The following work is intentionally outside canonical closure:

- ScytaleDroid integration
- Iapetus / deep-learning model work
- full Android permission lifecycle and API-level temporal semantics
- broader cross-system persistence orchestration beyond run/result storage
- a full operator-grade frozen-model inference UX

canonical should close with truthful reporting, bounded operator surfaces, and stable
reproducibility, not a platform redesign.

## Minimum artifact checklist

Each canonical profile run should emit:

- `label_contract_{run_id}.json/.md` — profile role, label namespace, claim surface
- `permission_pattern_contract_{run_id}.json/.md` — 0–9 structural pattern ladder
- `ml_sample_label_fact_{run_id}.csv` — supervised label fact for DL seeding
- `ml_permission_vocabulary_{run_id}.json` — alias normalization plus prevalence-derived
  permission tokens from permission-trends tables (v2 export)
- `ml_run_manifest_{run_id}.json` — curated seed manifest for Neptune/Iapetus prep
  (references label contract, pattern contract, sample label fact, vocabulary, pattern
  fact, and split export when present)
- `ml_permission_pattern_fact_{run_id}.csv` (when enrichment tables exist)
- `ml_train_validation_test_split_{run_id}.csv` (when split audit exists)
- `run_observability_summary.json` with `pipeline_status: PASS`

Canonical profiles and run slots:

| Profile | Run slot |
| --- | --- |
| `android_malware_all_current` | `allcurrent_diagnostic` |
| `android_malware_major_families` | `majorfam_benchmark` |
| `android_malware_type_taxonomy` | `typelevel_benchmark` |
| `android_malware_expanded_families` | `expandedfam_exploratory` |

Offline validation (no pipeline rerun):

```bash
python scripts/dev/validate_canonical_runs.py --verify-only --strict --runs-root artifacts/baselines/canonical_slots
```

CI always validates the checked-in fixture tree above. Local live slots under `output/runs/` are
validated additionally when present. Regenerate fixtures with
`python scripts/dev/build_canonical_slot_fixtures.py`.

Refresh live canonical slot handoff artifacts without rerunning the pipeline:

```bash
make refresh-canonical-handoff
```

`refresh-canonical-handoff` rewrites vocabulary counters, ensures `ml_train_validation_test_split`
when split audit exists, exports `dl_handoff_summary`, and backfills
`run_observability_summary.json` `dl_handoff` (including `dl_seed_status`). Slots without
`run_manifest.json` are skipped locally via `--skip-missing-slots`.

Validate live canonical slots (strict, skips absent slots):

```bash
make validate-canonical-live
```

Wait for an in-flight canonical slot to finalize, refresh handoff, and validate:

```bash
make wait-validate-majorfam
```

Manifest finalize **re-exports** `label_contract` from the effective cohort frame so
samples-stage contracts do not drift from benchmark-gated training pools.

## Release notes

Operator-facing caveat wording and canonical run IDs:
[`docs/RELEASE_NOTES.md`](RELEASE_NOTES.md).

## Tag readiness (2026-06-06)

Four canonical slot runs validated **TAG_READY** offline (`make verify-canonical` + strict
live-slot check): differentiated profile roles, 0–9 permission-pattern contract, DL
seed exports present, observability PASS with complete artifacts.

Canonical live run IDs (after `make refresh-canonical-handoff`):

| Profile | Slot | Run ID |
| --- | --- | --- |
| `android_malware_all_current` | `allcurrent_diagnostic` | `20260606T034155Z__46cd0b` |
| `android_malware_major_families` | `majorfam_benchmark` | `20260606T023207Z__4e3734` |
| `android_malware_type_taxonomy` | `typelevel_benchmark` | `20260606T002313Z__df1048` |
| `android_malware_expanded_families` | `expandedfam_exploratory` | `20260606T160145Z__014ac4` |

`make refresh-canonical-handoff` also backfills `cohort_funnel_plain` and operator claim
surfaces on completed runs without a pipeline rerun.

`ml_run_manifest_{run_id}.json` lists only seed files that exist; optional exports
live in `optional_seed_artifact_refs`. After vocabulary refresh, call
`sync_ml_run_manifest_seed_counters()` so `vocabulary_entry_count` and `dataset_hash`
match the v2 vocabulary export and run manifest.

Canonical profiles **hard-fail** when cohort persistence, dataset hash, research-validity
bundle export, ML seed export, or hygiene-bundle steps fail. Research-validity contract
report failures are no longer swallowed silently on canonical runs. `run_observability_summary.json`
now records `cohort_persistence_source`, `dataset_hash`, and `dl_handoff` paths.
(`ml_permission_pattern_fact`, `ml_train_validation_test_split`) are recorded under
`optional_seed_artifact_refs`. When runtime `samples_df` is unavailable at manifest
finalize, `ml_sample_label_fact` rebuilds from `aligned_labels_{run_id}.csv` or
`cohort_membership.csv` / `cohort_membership_{run_id}.csv` when the in-memory cohort
frame is unavailable. The samples stage persists both legacy and run-scoped membership
via `obsidiandroid.diagnostics.cohort_persistence`; manifest finalize reloads through
`resolve_effective_samples_df()` before dataset hash, research validity, and ML seeds.

Remaining deferrals stay in later release+ (deep learning, ScytaleDroid, frozen-model
inference UX).

## v2.2 research database (next milestone)

v2.2 adds a **dedicated curated research ledger** (`obsidiandroid_research`,
`OBSIDIANDROID_RESEARCH_DB_NAME`) separate from Erebus raw storage. v2.2.0 delivers
DDL drafts, a dry-run importer, and the sparse `ml_sample_permission_feature` export
spec — no live DB writes, web UI, Quasar, ScytaleDroid, or deep-learning training.

See [`docs/RESEARCH_DB_PLAN.md`](RESEARCH_DB_PLAN.md). Dry-run all canonical
fixture slots with `make dry-run-canonical-db-import`.
