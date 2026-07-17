# ObsidianDroid v2.2.0 — Release Notes

**Release type:** governed platform closure (with scientific caveats)  
**Not a publication-ready scientific benchmark tag.**

## Summary

This v2.2.0 release closes the Android malware classification and permission-pattern
research platform phase: four canonical profiles, manifest-backed observability,
0–9 structural permission-pattern contracts, and Neptune/Iapetus deep-learning seed
exports.

## Canonical validation runs

| Profile | Slot | Run ID | Macro-F1 | Claim status |
| --- | --- | --- | ---: | --- |
| `android_malware_all_current` | `allcurrent_diagnostic` | `20260606T034155Z__46cd0b` | 0.684 | MIXED |
| `android_malware_major_families` | `majorfam_benchmark` | `20260606T023207Z__4e3734` | 0.861 | MIXED |
| `android_malware_type_taxonomy` | `typelevel_benchmark` | `20260606T002313Z__df1048` | 0.554 | MIXED |
| `android_malware_expanded_families` | `expandedfam_exploratory` | `20260606T160145Z__014ac4` | 0.758 | MIXED |

All profiles: `pipeline_status: PASS`, `publication_ready: false`, `dl_seed_status: ready`.

### Profile roles

- **All-current** — current-corpus diagnostic / census surface
- **Major families** — support-gated major-family benchmark (n≥3)
- **Type taxonomy** — authoritative `type_slug` benchmark
- **Expanded families** — major + minor family exploratory stress surface

## What v2.2.0 supports

- Authority-aware cohort preparation and differentiated profile claim surfaces
- a canonical label contract and 0–9 permission-pattern contract per run
- Structural permission-pattern reporting (association strength, not malware proof)
- DL seed handoff (`ml_run_manifest`, label fact, vocabulary, pattern fact, split export)
- Offline strict validation: `make verify-canonical`

## What v2.2.0 does not claim

- Publication-ready family or type attribution
- Population-wide Android malware representativeness
- Deep-learning model performance (seed exports only)
- Permissions prove malware behavior, runtime causality, or dynamic-analysis findings
- Benign-app comparison or ATT&CK technique confirmation without runtime evidence

## Data-quality caveats

- **Family concentration:** Godfather-heavy cohorts; top-5 family share roughly 62–69% across profiles; majorfam Godfather ~42% of prepared cohort
- **Banker dominance:** type-taxonomy profile ~79% banker; Macro-F1 ~0.55 under severe class imbalance
- **All-current classifier pool:** 211 aligned rows excluded at trainable-pool filter (null/unmapped family labels)
- **Vendor leakage risk:** parsed vendor-family strings can exceed leakage-safe vendor baselines (expandedfam delta ~0.19 Macro-F1)
- **Observability funnel text:** pre-canonical finalize runs may show legacy wording until `make refresh-canonical-handoff` backfills `cohort_funnel_plain` (no full pipeline rerun required)

## Deferred beyond v2.2.0

- `ml_sample_permission_feature` export
- Quasar dataset-readiness views in-repo
- Frozen-model inference UX
- Dynamic-analysis integration / ScytaleDroid
- Full cross-system persistence orchestration beyond run-scoped storage

## Validation

```bash
make ci
make verify-canonical
make refresh-canonical-handoff
PYTHONPATH=src python scripts/dev/validate_canonical_runs.py --verify-only --strict --skip-missing-slots
```

CI validates checked-in fixtures under `artifacts/baselines/canonical_slots/`.
Regenerate from live slots with:

```bash
PYTHONPATH=src python scripts/dev/build_canonical_slot_fixtures.py
```
