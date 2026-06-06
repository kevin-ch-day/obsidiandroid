# ObsidianDroid Database Plan (V3.1 direction)

**Status:** V3.1.0 draft — approved decisions locked; DDL draft + dry-run importer skeleton delivered. No runtime DB writes, web UI, Quasar, ScytaleDroid, or deep-learning training in this phase.

**Context:** ObsidianDroid **v3.0.0** closed the governed platform and artifact contract. V3.1 defines a **dedicated ObsidianDroid research database** that persists curated outputs separately from Erebus.

---

## 1. Purpose of the ObsidianDroid database

### What it is

A **dedicated MySQL/MariaDB schema** named **`obsidiandroid_research`** (env **`OBSIDIANDROID_RESEARCH_DB_NAME`**) that stores **curated Android malware research state** produced by ObsidianDroid runs. This name makes clear the ledger is ObsidianDroid research output, not raw Erebus storage.

It is **not** a replacement for Erebus. It is the **downstream research ledger** for:

- governed run manifests and release pointers
- profile-scoped sample membership and curation decisions
- supervised label facts as used in training (not raw vendor strings)
- permission vocabulary and per-sample permission facts frozen per run
- permission-pattern facts and contracts
- model metrics, predictions, quality flags, and split assignments
- audit artifacts needed for benchmark replay and dataset curation

### What it enables (future, not V3.1 implementation)

| Capability | How the DB helps |
| --- | --- |
| Benchmark replay | `runs` + `release_manifests` + `split_assignments` reproduce frozen cohorts without re-parsing `output/runs/` trees |
| Permission-pattern analysis | `permission_pattern_facts` + `permission_vocabulary` support cross-run queries without reloading bundles |
| Deep learning (Neptune/Iapetus) | `sample_label_facts`, `sample_permission_facts`, `split_assignments` replace ad-hoc CSV joins |
| Dataset curation | `profile_membership` + `quality_flags` encode benchmark vs exploratory vs diagnostic-only posture |
| Operator audit | `model_metrics`, `prediction_facts`, taxonomy mismatch imports support MIXED-claim review |

### Design principles

1. **Curated truth only** — store what ObsidianDroid asserts for a run after governance gates, not raw VT noise.
2. **Run-scoped immutability** — each `run_id` is an append-only research snapshot; corrections are new runs or explicit supersede rows, not silent overwrites of Erebus.
3. **Reference upstream by stable keys** — `sample_id`, `sha256`, `dataset_hash`, `split_hash`; do not duplicate full VT payloads.
4. **Artifact parity** — every persisted row should trace to a V3 artifact path or an explicit derivation rule documented in `release_manifests`.

---

## 2. Ownership boundaries

### Stays in Erebus (read-only to ObsidianDroid)

| Domain | Examples | ObsidianDroid access |
| --- | --- | --- |
| Sample catalog | `sample_id`, `sha256`, package, VT timestamps, catalog semantics | **SELECT / reference** |
| Raw VT enrichment | scan state, engine verdict tables, consensus metadata | **SELECT** for cohort SQL only |
| Raw AV detections | per-engine vendor strings, detection names | **SELECT**; never persisted as curated truth in ObsidianDroid DB |
| IOC imports | external feed rows, ingest queues | **None** (Erebus operator domain) |
| Family/type authority source | authority tables, vendor-evidence layers, `v_android_sample_family_type_authority` | **SELECT**; authority *decisions* for a run are copied into `sample_label_facts` / `quality_flags` as **run outputs** |
| Broad threat-intel state | non-Android lanes, cross-platform objects | **Exclude** from ObsidianDroid research schema |

### Belongs in ObsidianDroid research DB

| Domain | Examples |
| --- | --- |
| Run governance | `runs`, `profiles`, `release_manifests`, claim readiness summaries |
| Curated labels | `sample_label_facts`, `profile_membership`, curation states |
| Permission research | `permission_vocabulary`, `sample_permission_facts`, `permission_pattern_facts` |
| Model research | `model_metrics`, `prediction_facts`, `split_assignments` |
| Quality / audit | `quality_flags`, taxonomy mismatch imports, concentration warnings |

### Stays in Permission Intel (read-only)

| Domain | ObsidianDroid DB behavior |
| --- | --- |
| Live `android_permission_*` observations | Read during export/build; persist **run-frozen** rows in `sample_permission_facts` |
| Permission dictionaries / risk tiers | Copy **run-scoped vocabulary** into `permission_vocabulary`; do not mirror full PI schema |

### Reference by ID/hash — do not copy

| Field | Store in ObsidianDroid DB | Do not copy |
| --- | --- | --- |
| `sample_id` | Yes (FK key) | — |
| `sha256` | Yes (denormalized for audit) | Full APK/metadata blobs |
| `dataset_hash` | Yes on `runs` | Feature matrix CSV/GZ |
| `split_hash` | Yes on `runs` / `split_assignments` | Entire split audit file (optional path in manifest JSON) |
| `family_id` / `type_slug` | Yes as **governed training labels** | Raw VT family strings as primary truth |
| Vendor detection text | **No** in curated tables | Use `quality_flags` + `audit_only` membership |
| VT engine verdict rows | **No** | Query Erebus when needed |
| Permission observations | **Frozen long-form** in `sample_permission_facts` | Continuous PI replication |

### Anti-patterns (explicitly out of scope)

- Turning ObsidianDroid DB into a second Erebus VT warehouse
- Writing back into Erebus or Permission Intel source tables
- Storing full `aligned_features_*.csv.gz` wide matrices in SQL (use long-form `sample_permission_facts` + optional object storage later)
- Quasar / web UI tables in V3.1

---

## 3. First schema proposal

**Convention:** clean table names, no `od_` prefix. All tables live in the **ObsidianDroid research schema** only.

**Column types:** MySQL 8+ / MariaDB 10.6+; `JSON` for manifest fragments; `CHAR(64)` for hashes; `DATETIME(6)` UTC for run timestamps.

### `profiles`

| Aspect | Detail |
| --- | --- |
| **Purpose** | Canonical execution profiles (`android_malware_major_families`, etc.) and their claim surface role |
| **Key columns** | `profile_id` PK; `profile_role`; `claim_surface_code`; `training_label_field`; `support_floor_mode`; `run_slot`; `yaml_path`; `active_from_utc`; `retired_at_utc` |
| **Source** | `profiles/*.yaml`, `v3_label_contract_*.json` |
| **V3.1** | **Required** (seed rows for four canonical profiles) |
| **Truth type** | Curated configuration truth |

### `runs`

| Aspect | Detail |
| --- | --- |
| **Purpose** | One row per `run_id` / `run_instance_id`; anchor for all run-scoped facts |
| **Key columns** | `run_id` PK; `profile_id` FK; `run_slot`; `run_mode`; `run_started_at_utc`; `run_finished_at_utc`; `pipeline_status`; `claim_status`; `publication_ready`; `dataset_hash`; `split_hash`; `cohort_size`; `train_n`; `test_n`; **`source_git_commit`**; **`source_git_tag`**; **`code_version`**; `manifest_json`; `observability_json`; `artifact_root` |
| **Source** | `run_manifest.json`, `run_observability_summary.json`, `claim_readiness_summary_{run_id}.json`; optional git metadata from operator or release backfill |
| **V3.1** | **Required** |
| **Truth type** | Run output + governance summary |

### `samples`

| Aspect | Detail |
| --- | --- |
| **Purpose** | **Lazy curated** Android sample identity registry within ObsidianDroid research (not Erebus catalog replication) |
| **Key columns** | `sample_id` PK; `sha256` UNIQUE; `first_seen_run_id`; `last_seen_run_id`; `package_name`; `erebus_row_hash` (optional content hash for drift detection) |
| **Source** | Insert **only** when `sample_id` appears in curated run artifacts: label facts, profile membership, permission facts, prediction facts, or release manifests. **Do not bulk-copy** every Erebus sample. |
| **V3.1** | **Required** (lazy registry) |
| **Truth type** | Reference registry |

### `sample_label_facts`

| Aspect | Detail |
| --- | --- |
| **Purpose** | Governed supervised labels as used for a specific run |
| **Key columns** | `run_id` FK; `sample_id` FK; `profile_id`; `family_id`; `family_canonical`; `type_slug`; `supervised_label`; `supervised_label_namespace`; `training_label_field`; `sample_label_kind`; PK (`run_id`, `sample_id`) |
| **Source** | `ml_sample_label_fact_{run_id}.csv`, `v3_label_contract_{run_id}.json` |
| **V3.1** | **Required** |
| **Truth type** | Curated run truth |

### `profile_membership`

| Aspect | Detail |
| --- | --- |
| **Purpose** | Per-run cohort membership and **curation state** for each sample |
| **Key columns** | `run_id`; `profile_id`; `sample_id`; `membership_stage` (`sql_governed` / `prepared` / `aligned` / `trainable` / `train` / `test`); `curation_state` (see §6); `benchmark_eligible`; `trainable_pool_included`; `exclusion_reason`; PK (`run_id`, `sample_id`) |
| **Source** | `ml_train_validation_test_split_{run_id}.csv`, `cohort_funnel.csv`, `dataset_foundation_summary.json`, training attrition metadata |
| **V3.1** | **Required** |
| **Truth type** | Curated run truth + policy flags |

### `permission_vocabulary`

| Aspect | Detail |
| --- | --- |
| **Purpose** | Run-scoped permission token normalization used by exports and pattern facts |
| **Key columns** | `run_id`; `vocabulary_version`; `entry_kind` (`alias` / `permission`); `permission`; `canonical_permission`; `alias_from`; `alias_to`; `source_scope`; `max_prevalence_pct`; PK (`run_id`, `entry_kind`, `canonical_permission`, `permission`) |
| **Source** | `ml_permission_vocabulary_{run_id}.json`, `permission_alias_map_*.json` |
| **V3.1** | **Required** |
| **Truth type** | Run-frozen derived vocabulary |

### `sample_permission_facts`

| Aspect | Detail |
| --- | --- |
| **Purpose** | Long-form per-sample permission presence for DL and SQL analytics |
| **Key columns** | `run_id`; `sample_id`; `permission_name`; `canonical_permission`; `permission_present` (0/1); `permission_authority_bucket`; `permission_risk_tier`; `permission_source`; `feature_column_name` (e.g. `perm__android_permission_internet`); PK (`run_id`, `sample_id`, `permission_name`) |
| **Source** | **New** `ml_sample_permission_feature_{run_id}.csv` (§5); optional join metadata from PI |
| **V3.1** | **Required** (after export exists) |
| **Truth type** | Run-frozen derived features |

### `permission_pattern_facts`

| Aspect | Detail |
| --- | --- |
| **Purpose** | Normalized 0–9 permission-pattern ladder rows at type/family/enrichment surfaces |
| **Key columns** | `run_id`; `fact_grain` (`type_enrichment` / `family_enrichment` / `similarity` / …); `focus_key` (type_slug or family); `permission`; `comparison_scope`; `pattern_score`; `pattern_level`; `pattern_label`; `pattern_basis`; `pattern_confidence`; `pattern_reason`; `source_artifact` |
| **Source** | `ml_permission_pattern_fact_{run_id}.csv`, permission-trends bundle tables |
| **V3.1** | **Required** |
| **Truth type** | Run output (derived metrics) |

### `model_metrics`

| Aspect | Detail |
| --- | --- |
| **Purpose** | Headline and ablation model metrics per run |
| **Key columns** | `run_id`; `model_name`; `label_target`; `experiment` / `feature_set`; `macro_f1`; `weighted_f1`; `accuracy`; `primary_metric_name`; `primary_metric_value`; `split_hash`; `train_n`; `test_n`; PK (`run_id`, `model_name`, `label_target`, `experiment`) |
| **Source** | `model_comparison_summary_{run_id}.csv`, `ablation_summary_{run_id}.csv`, `run_manifest.json` `model_summary` |
| **V3.1** | **Required** |
| **Truth type** | Derived metrics |

### `prediction_facts`

| Aspect | Detail |
| --- | --- |
| **Purpose** | Per-sample prediction outcomes for failure analysis |
| **Key columns** | `run_id`; `sample_id`; `model_name`; `true_label`; `predicted_label`; `confidence`; `prediction_error`; `shared_malware_type`; `type_guard_suppressed`; PK (`run_id`, `sample_id`, `model_name`) |
| **Source** | `prediction_errors_{run_id}.csv`, structured label resolution exports |
| **V3.1** | **Recommended** (audit-heavy profiles) |
| **Truth type** | Run output |

### `quality_flags`

| Aspect | Detail |
| --- | --- |
| --- | --- |
| **Purpose** | Row- or run-level quality / claim blockers |
| **Key columns** | `run_id`; `sample_id` NULLABLE; `flag_scope` (`run` / `sample` / `family`); `flag_code`; `severity`; `flag_value`; `rationale`; `source_artifact` |
| **Source** | `dataset_quality_gates.csv`, `taxonomy_consistency_mismatches_{run_id}.csv`, `claim_readiness_summary_{run_id}.json`, concentration warnings |
| **V3.1** | **Required** (at least run-level flags) |
| **Truth type** | Audit / quality flags |

### `split_assignments`

| Aspect | Detail |
| --- | --- |
| **Purpose** | Frozen train/test (and validation if present) membership |
| **Key columns** | `run_id`; `sample_id`; `split_role` (`train` / `test` / `val`); `split_hash`; `label_field`; `label_target`; `active_class_count`; `overlap_flag`; PK (`run_id`, `sample_id`) |
| **Source** | `ml_train_validation_test_split_{run_id}.csv`, split audit CSV |
| **V3.1** | **Required** |
| **Truth type** | Run-frozen assignment |

### `release_manifests`

| Aspect | Detail |
| --- | --- |
| **Purpose** | **Official release packaging** and git tag relationships; authoritative link between tagged releases and canonical runs |
| **Key columns** | `release_tag` (e.g. `v3.0.0`); `profile_id`; `run_id`; `git_commit`; `git_tag`; `code_version`; `importer_version`; `imported_at_utc`; `manifest_json` (artifact paths, hashes, notes); PK (`release_tag`, `profile_id`) |
| **Source** | Git tag + canonical slot `run_manifest.json` + `ml_run_manifest_{run_id}.json` |
| **V3.1** | **Required** for documenting v3.0.0 backfill |
| **Truth type** | Release audit / manifest |

**Git provenance split:** `runs` may carry optional `source_git_commit`, `source_git_tag`, and `code_version` for run-local traceability; `release_manifests` owns official release packaging and tag relationships.

### Optional future tables (not V3.1)

| Table | When |
| --- | --- |
| `contracts` | If label/pattern contracts need query without JSON files |
| `ablation_grid` | If ablation CSVs need normalized child table beyond `model_metrics` |
| `importer_runs` | When dry-run importer gets execution history |

---

## 4. V3 artifact importer (dry-run skeleton, V3.1.0)

**Script:** `scripts/import_v3_run_to_db.py`  
**Mode:** dry-run only in V3.1.0 — validates run folders and prints an import plan; **no database writes**. Future `--apply` is deferred past V3.1.0.

### Inputs

| Argument | Purpose |
| --- | --- |
| `--run-root` | Path to `output/runs/{slot}/` or archived run tree |
| `--run-id` | Override when manifest disagrees with directory |
| `--profile-id` | Validation against manifest |
| `--release-tag` | Optional; writes `release_manifests` row |
| `--dry-run` | Parse + validate + print row counts; **no INSERT** |

### Read order (idempotent per `run_id`)

1. `run_manifest.json` → `runs`, `profiles` upsert
2. `run_observability_summary.json` → enrich `runs`, run-level `quality_flags`
3. `claim_readiness_summary_{run_id}.json` → `runs.claim_status`, `quality_flags`
4. `v3_label_contract_{run_id}.json` → contract metadata on `runs.manifest_json` or future `contracts`
5. `permission_pattern_contract_{run_id}.json` → contract metadata
6. `ml_sample_label_fact_{run_id}.csv` → `samples`, `sample_label_facts`
7. `ml_permission_vocabulary_{run_id}.json` → `permission_vocabulary`
8. `ml_sample_permission_feature_{run_id}.csv` → `sample_permission_facts` (when export exists)
9. `ml_permission_pattern_fact_{run_id}.csv` → `permission_pattern_facts`
10. `ml_train_validation_test_split_{run_id}.csv` → `split_assignments`, `profile_membership`
11. `model_comparison_summary_{run_id}.csv` + `ablation_summary_{run_id}.csv` → `model_metrics`
12. `prediction_errors_{run_id}.csv` → `prediction_facts`
13. `taxonomy_consistency_mismatches_{run_id}.csv` → `quality_flags`

### Dry-run report (implemented in V3.1.0)

The importer prints (or emits `--json`):

| Section | Content |
| --- | --- |
| Run detected | `run_id`, `profile_id`, `run_root`, `diagnostics/` path |
| Profile detected | canonical profile validation (warning if non-canonical) |
| Artifacts | required present/missing; optional present/missing |
| Planned rows | per-table insert counts in FK-safe order |
| Lazy registry | unique `sample_id` count across curated artifacts |
| Blocking errors | missing required artifacts (strict), `run_id`/`profile_id` mismatch, duplicate `sample_id`, non-tag-ready `pipeline_status` |
| Warnings | stale manifest counters, missing split export, missing permission feature export, non-canonical profile |

### Validation gates (dry-run must fail loud)

- `dataset_hash` / `split_hash` present when split export exists (warning if split present but hash missing)
- `sample_id` uniqueness within run
- Row counts match manifest `sample_label_rows`, `vocabulary_entry_count` (warning on drift)
- `profile_id` matches canonical profile registry (warning if outside four canonical profiles)
- No apply if `pipeline_status` not in `{PASS, PASS_WITH_WARNINGS}` unless `--allow-mixed` (operator override)

### Non-goals for importer v0 (V3.1.0)

- No database INSERT/UPDATE/DELETE
- No live Erebus writes
- No automatic scheduling
- No deletion of prior `run_id` rows (append-only when `--apply` exists)

---

## 5. `ml_sample_permission_feature_{run_id}.csv` export spec

### Why it is needed

V3 already exports wide feature matrices (`aligned_features_{run_id}.csv.gz`) and permission vocabulary, but Neptune/Iapetus and `sample_permission_facts` need a **stable, sparse long-form, run-scoped** permission table without loading 1000+ `perm__*` columns. **Dense wide matrices are not the database source of truth**; they may be generated later for ML workloads.

### Canonical export shape (sparse long-form)

**Minimum required columns** (V3.1.0 contract):

| Column | Type | Source |
| --- | --- | --- |
| `run_id` | string | `RUNTIME_RUN_ID` |
| `profile_id` | string | profile YAML |
| `sample_id` | int | cohort frame |
| `sha256` | string | cohort / label fact |
| `permission_name` | string | PI observation or normalized permission string |
| `permission_present` | 0/1 | from `perm__*` column or PI observation |
| `permission_authority_bucket` | enum/string | PI governance bucket when available; else `unknown` |
| `permission_risk_tier` | string | PI / `obsidiandroid.risk_band` mapping when available |
| `permission_source` | string | e.g. `permission_intel`, `manifest_declared`, `inferred` |

**Recommended optional columns** (import-friendly, not blocking V3.1.0):

| Column | Purpose |
| --- | --- |
| `canonical_permission` | `ml_permission_vocabulary` lookup |
| `feature_column_name` | original fused `perm__*` column for traceability |

Optional future columns: `permission_group`, `dangerous_flag`, `observed_at_utc`.

### Export rules

1. **Sparse only** — one row per (`sample_id`, `permission_name`) where the permission is observed or explicitly scored; do not emit a full dense cross-product of all samples × all vocabulary permissions as the canonical artifact.
2. **Feeds `sample_permission_facts`** — the CSV is the run-frozen handoff; DB import maps columns directly without re-querying Permission Intel.
3. **Dense/wide matrices** — may be derived offline from this export or from `aligned_features_{run_id}.csv.gz` for ML teams; never persisted as SQL source of truth.

### Implementation path (deferred to V3.1.1+)

**Primary source (recommended):** post-alignment fused feature matrix (`aligned_features_{run_id}.csv.gz` or in-memory frame at ML seed export time).

1. Select columns matching `perm__*`.
2. Melt to sparse long format.
3. Map `feature_column_name` → `permission_name` / `canonical_permission` via `permission_alias_map_*.json`.
4. Join `sha256` from `ml_sample_label_fact` or cohort frame.
5. Enrich authority/risk/source from Permission Intel **at export time** (read-only).

**Export hook:** extend `export_ml_seed_artifacts()` in `ml_seed_exports.py`; register in `ml_run_manifest` `optional_seed_artifact_refs` until promoted to required for live DB import.

---

## 6. Curation / pruning policy

### Curation states (initial enum)

| State | Meaning |
| --- | --- |
| `benchmark_include` | Eligible for support-gated benchmark training and benchmark-claim surfaces |
| `exploratory_include` | Eligible for expanded-family / stress training; stronger caveats in claims |
| `diagnostic_only` | In prepared cohort and diagnostics, but not suitable for strong supervised family claims |
| `audit_only` | Retained for taxonomy/vendor audit; excluded from training and claims |
| `needs_review` | Curated artifact present but curation posture not yet decided; blocks benchmark/training promotion until resolved |
| `exclude_from_training` | Dropped at classifier trainable-pool or min-support gate |
| `exclude_from_claims` | May be trained but must not support publication-style or population claims |

### Application matrix

| Condition | Typical state | Notes |
| --- | --- | --- |
| Major-family profile, family n≥3, trainable pool | `benchmark_include` | `android_malware_major_families` |
| Expanded-family profile, trainable pool | `exploratory_include` | MIXED claims still apply |
| All-current prepared cohort, concentration_warn | `diagnostic_only` | Census / exploratory surface |
| Weak `sample_label_kind`, unmapped vendor tokens | `audit_only` | Raw vendor strings never primary labels |
| Low-support family rows (training drop) | `exclude_from_training` | From training filter / `low_support` attrition |
| Null `family_id` / authority filter drop | `exclude_from_training` | e.g. all-current −211 pool |
| `concentration_warning` or `supervised_family_claims_suitable=false` | `exclude_from_claims` (run-level flag) | Does not remove rows; blocks claim posture |
| Raw-vs-canonical family conflicts | `audit_only` or `diagnostic_only` | `quality_flags` + `taxonomy_consistency_mismatches` |
| Non-Android lane rows | `exclude_from_training` + `exclude_from_claims` | SQL gate excluded; if leaked, hard flag |
| Generic / filename / hash-only labels | `audit_only` | Never `benchmark_include` |
| Godfather-scale source batch pockets | `diagnostic_only` unless profile is benchmark-gated and family eligible | Document concentration in `quality_flags` |
| Type-guard suppressed predictions | `audit_only` on prediction_facts | Cross-type family suppression |

### Run-level vs sample-level

- **Run-level:** `claim_status=MIXED`, `publication_ready=false`, concentration → `quality_flags` on `runs`
- **Sample-level:** `profile_membership.curation_state` + `exclusion_reason`
- **Importer rule:** never upgrade curation state silently; default from profile `support_floor_mode` + split role + label fact completeness

---

## 7. V3.1.0 milestone (delivered)

Database-first slice — **plan + DDL draft + dry-run importer + export spec**; no production writes.

| Deliverable | Status |
| --- | --- |
| `docs/OBSIDIANDROID_DB_PLAN.md` | Updated with approved decisions |
| `database/sql/obsidiandroid/001_create_core_tables.sql` | DDL draft — 13 tables, FKs, git provenance |
| `database/sql/obsidiandroid/002_create_indexes.sql` | Secondary indexes |
| `database/sql/obsidiandroid/003_create_views.sql` | Convenience views (draft) |
| `database/sql/obsidiandroid/README.md` | Schema/env conventions |
| `scripts/import_v3_run_to_db.py` | Dry-run skeleton — single slot (`--run-root`) or batch (`--runs-root`) |
| `tests/test_import_v3_run_to_db.py` | Contract tests for fixture slots and blocking gates |
| `make dry-run-v3-db-import` | Batch dry-run on `artifacts/baselines/v3_canonical_slots` |
| `artifacts/baselines/v3_db_import_dry_run_fixture_slots.json` | Frozen batch dry-run baseline for fixture slots |

**Environment contract:** `OBSIDIANDROID_RESEARCH_DB_NAME` (default `obsidiandroid_research`), documented in [`docs/data_sources.md`](data_sources.md).

### Explicitly deferred past V3.1.0

- Live importer `--apply` and runtime pipeline DB writes during `stage_manifest`
- `ml_sample_permission_feature` pipeline export implementation
- Web UI / Quasar
- ScytaleDroid integration
- Deep-learning training jobs
- Automatic backfill of all historical `output/runs/*` trees (manual canonical four-run dry-run first)

### Suggested next steps after V3.1.0 review

1. Apply DDL to a dev MySQL instance
2. Dry-run all four v3.0.0 canonical slots with `--release-tag v3.0.0`
3. Implement `ml_sample_permission_feature` sparse export (V3.1.1)
4. Add importer `--apply` behind explicit flag + DB preflight
5. Backfill `release_manifests` for `v3.0.0`

---

## Appendix: v3.0.0 canonical runs (reference)

| Profile | Run ID |
| --- | --- |
| `android_malware_all_current` | `20260606T034155Z__46cd0b` |
| `android_malware_major_families` | `20260606T023207Z__4e3734` |
| `android_malware_type_taxonomy` | `20260606T002313Z__df1048` |
| `android_malware_expanded_families` | `20260606T160145Z__014ac4` |

Scientific posture remains **MIXED** on all profiles; the database stores that truth explicitly and does not reinterpret it as publication-ready.

---

## Resolved decisions (V3.1.0)

| Decision | Resolution |
| --- | --- |
| Schema / env name | `obsidiandroid_research` + `OBSIDIANDROID_RESEARCH_DB_NAME` |
| Table naming | Clean names, no `od_` prefix |
| `samples` registry | Lazy — insert only from curated run artifacts |
| Permission export | Sparse long-form `ml_sample_permission_feature_{run_id}.csv` |
| Git provenance | Optional fields on `runs`; official packaging in `release_manifests` |
| DDL location | `database/sql/obsidiandroid/` (`001`–`003` + README) |
| Importer | Dry-run skeleton only in V3.1.0 |
| Curation states | Seven states including `needs_review` |

## Open design questions

1. **MySQL deployment** — shared instance with Erebus vs dedicated host; operator grants and backup policy.
2. **`profile_membership` derivation** — exact rules when `ml_train_validation_test_split` is missing (provisional: label-fact row count with `needs_review` default?).
3. **`sha256` enrichment** — lazy registry: require Erebus lookup at import time vs allow NULL until enriched.
4. **`prediction_facts` requirement** — recommended vs required for v3.0.0 canonical backfill.
5. **Sparse export boundary** — emit `permission_present=0` rows for declared-absent permissions, or only present=1 rows?
6. **Live importer connection settings** — whether research DB reuses `OBSIDIAN_DB_*` host/credentials with a different schema name or gets its own `OBSIDIANDROID_RESEARCH_DB_*` tuple.
4. **`prediction_facts` requirement** — recommended vs required for v3.0.0 canonical backfill.
