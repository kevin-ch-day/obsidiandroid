# `ml_sample_permission_feature_{run_id}.csv` export spec

**Status:** implemented in V3.1.1 (`export_ml_seed_artifacts()`). Present-only sparse rows; offline authority/risk defaults (`unknown` / `aligned_features`).

**Related:** [`OBSIDIANDROID_DB_PLAN.md`](OBSIDIANDROID_DB_PLAN.md) §5, table `sample_permission_facts`, DDL under `database/sql/obsidiandroid/`.

---

## Purpose

Provide a **sparse, long-form, run-scoped** permission handoff for:

- `sample_permission_facts` database import
- Neptune / Iapetus deep-learning seed joins (future)
- SQL analytics without loading wide `perm__*` feature matrices

Dense wide matrices (`aligned_features_{run_id}.csv.gz`) may still exist for ML, but they are **not** the database source of truth.

---

## File naming

```
ml_sample_permission_feature_{run_id}.csv
```

Registered in `ml_run_manifest_{run_id}.json` under `optional_seed_artifact_refs` until promoted to required for live DB import.

---

## Required columns (minimum contract)

| Column | Type | Description |
| --- | --- | --- |
| `run_id` | string | Governed run identifier (`RUNTIME_RUN_ID`) |
| `profile_id` | string | Execution profile (e.g. `android_malware_major_families`) |
| `sample_id` | int | Erebus catalog sample id |
| `sha256` | string | APK hash for audit (from cohort / label fact) |
| `permission_name` | string | Normalized permission token |
| `permission_present` | 0/1 | Whether permission is present for this sample in the run |
| `permission_authority_bucket` | string | PI governance bucket when available; else `unknown` |
| `permission_risk_tier` | string | Risk band from PI / `obsidiandroid.risk_band` when available |
| `permission_source` | string | Provenance, e.g. `permission_intel`, `manifest_declared`, `inferred` |

---

## Recommended optional columns

| Column | Purpose |
| --- | --- |
| `canonical_permission` | Resolved token via `ml_permission_vocabulary_{run_id}.json` |
| `feature_column_name` | Original fused column (e.g. `perm__android_permission_internet`) |

Future optional columns (non-blocking): `permission_group`, `dangerous_flag`, `observed_at_utc`.

---

## Export rules

1. **Present-only sparse long-form** — one row per (`sample_id`, `permission_name`) where the aligned `perm__*` value is `> 0`. Do not emit zero rows or a full dense cross-product of samples × vocabulary.
2. **Run-frozen values** — V3.1.1 uses offline defaults (`permission_authority_bucket=unknown`, `permission_risk_tier=unknown`, `permission_source=aligned_features`). Live Permission Intel enrichment is deferred.
3. **Feeds `sample_permission_facts`** — column names map directly to the research DB table (see `001_create_core_tables.sql`).
4. **Dense melt is derived** — wide matrices for ML teams may be generated offline from this export or from `aligned_features_{run_id}.csv.gz`; never persisted as SQL truth.

---

## Primary implementation source (V3.1.1)

1. Read post-alignment fused features (`aligned_features_{run_id}.csv.gz` or in-memory frame at ML seed export).
2. Select `perm__*` columns.
3. Melt to sparse long format.
4. Map columns through `permission_alias_map_{run_id}.json` / `ml_permission_vocabulary_{run_id}.json`.
5. Join `sha256` from `ml_sample_label_fact_{run_id}.csv`.
6. Enrich authority/risk/source from Permission Intel at export time.

**Export hook:** `export_ml_seed_artifacts()` in `src/obsidiandroid/diagnostics/ml_seed_exports.py` writes the CSV and registers it under `ml_run_manifest` `optional_seed_artifact_refs`.

**Fallback:** rebuild from `cohort_membership.csv` + PI observation query (slower; mark `permission_source=permission_intel_live`).

---

## Dry-run importer behavior (V3.1.0)

`scripts/import_v3_run_to_db.py` reports the artifact as optional. When missing, `sample_permission_facts` planned row count is `0` and a warning is emitted. No database writes occur in V3.1.0.
