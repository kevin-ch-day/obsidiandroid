# Data Sources and Integrations

This guide documents the datasets that ObsidianDroid consumes, how they are synchronized, and the safeguards required to keep the malware labeling pipeline trustworthy. Operators should review this reference before onboarding new feeds or refreshing replicated tables.

## Source of Truth

ObsidianDroid does **not** call live VirusTotal APIs during execution. Instead, it reads from project-controlled MySQL schemas. **Sample catalog, VirusTotal mirrors, and vendor verdicts** live in the primary Erebus database. **Android permission intelligence** (`android_permission_*` tables) lives in the separate Permission Intel database (see below). Together they are the authoritative source for:

- Vendor detections and metadata that drive label harmonization.
- Permission observations and enrichment used for permission features and permission-trend reporting.
- Historical engine performance measurements used in weighting and consensus scoring.

## Database Layout (split model)

ObsidianDroid consumes two **upstream read-only** logical databases on the same
MySQL/MariaDB instance in typical deployments. A third, dedicated
ObsidianDroid Core database holds separately governed downstream evidence.
Core schema provisioning, controlled fixture import, native analysis
persistence, and operational assessment have distinct lifecycle and approval
boundaries; do not infer current production row counts or enabled writers from
an older phase checkpoint. Configure source schema names with
`OBSIDIAN_DB_NAME` (primary) and
`OBSIDIAN_PERMISSION_INTEL_DB_NAME` (Permission Intel). The core connection
uses its own required `OBSIDIANDROID_CORE_DB_*` credentials and defaults only
its database name to `obsidiandroid_core_prod`; it never falls back to primary
source credentials.

### Primary Erebus database (`OBSIDIAN_DB_NAME`, default `erebus_threat_intel_prod`)

| Schema area | Key tables / views | Purpose |
| --- | --- | --- |
| Sample catalog | `malware_sample_catalog`, `malware_artifact_hash_registry` | Canonical sample identities, hashes, APK metadata, VT timestamps, package names, and catalog permission counts. |
| Family/type taxonomy | `v_android_apk_family_resolved`, `android_malware_family`, `android_malware_type` | Canonical malware family and type assignments used for cohort building and supervised labels. |
| VirusTotal summaries | `virustotal_sample_scan_summary`, `virustotal_sample_signal_current` | Per-sample detection totals, tags, reputation, and current VT-derived summary fields. |
| VirusTotal verdict matrix | `virustotal_sample_vendor_engine_verdicts` | Wide per-sample vendor verdict table used to build parser inputs and AV feature matrices. |
| Vendor metadata | `virustotal_vendor_engines` | Canonical vendor names plus trusted/active flags used during engine scoring and governance. |

Planned authority-layer extensions for the primary Erebus database are documented in
[`LABEL_AUTHORITY_SCHEMA_PLAN.md`](LABEL_AUTHORITY_SCHEMA_PLAN.md). Those objects are
intended to separate:

- governed family/type authority,
- raw vendor label evidence,
- generic label policy,
- temporal anchor provenance.

Current additive Erebus catalog-semantics fields that ObsidianDroid diagnostics may
consume when present include:

- `analysis_lane`
- `payload_target_platform`
- `payload_target_source`
- `sample_label_kind`
- `vt_family_token`
- `unknown_artifact_kind`
- `observed_filename`

These fields are **diagnostic/contextual inputs only** in current ObsidianDroid usage.
They do not replace Android cohort gating (`platform='android'` + `file_extension='apk'`)
or family/type authority from the Android taxonomy layer.

### Permission Intel database (`OBSIDIAN_PERMISSION_INTEL_DB_NAME`, default `android_permission_intel`)

The table inventory below describes storage ownership, not current research-reader
privileges. On the V2-gated production host, recovered evidence is consumed through
the separately approved exact export. Direct legacy observation/current-enrichment
reads remain denied. Do not restore broad PI grants to run old cross-schema queries.
The source contract preserves unresolved provider occurrences, not inferred manifest
truth. See [runtime access policy](runtime_source_connection_policy.md).

The rows below name versioned contracts, not a verified live schema inventory.

| Schema area | Key tables | Purpose |
| --- | --- | --- |
| Android permissions | `android_permission_obs_sample`, `android_permission_dict_aosp`, `android_permission_dict_oem`, `android_permission_dict_unknown`, `android_permission_meta_oem_vendor`, `android_permission_enrich_vt_current`, `android_permission_enrich_vt_event` | Observed permission rows, dictionaries, OEM metadata, and enrichment used by permission-trend reporting and ML permission features. |

On `android_permission_obs_sample`, the observation timestamp column is **`observed_at_utc`** (not `record_created_at_utc`). Diagnostics and SQL should use that name when filtering or ordering PI observation rows.

Cross-schema reporting joins (for example banking trojan permission extracts) qualify both databases in SQL (e.g. ``primary.malware_sample_catalog`` joined to ``android_permission_intel.android_permission_obs_sample``). ObsidianDroid does **not** assume live `android_permission_*` tables exist in the primary database.

### ObsidianDroid Core database (`OBSIDIANDROID_CORE_DB_*`, default schema `obsidiandroid_core_prod`)

The core database is a downstream evidence store, not an upstream source. It
is disabled by default and its connection preflight fails closed until the
reviewed schema ledger exists. Configure it only with a dedicated account:

- `OBSIDIANDROID_CORE_DB_HOST`
- `OBSIDIANDROID_CORE_DB_PORT` (default `3306`)
- `OBSIDIANDROID_CORE_DB_NAME` (default `obsidiandroid_core_prod`)
- `OBSIDIANDROID_CORE_DB_USER`
- `OBSIDIANDROID_CORE_DB_PASSWORD`
- `OBSIDIANDROID_CORE_PERSISTENCE_ENABLED` (default `false`; enable only for a separately reviewed runtime scope)

| Schema area | Key tables | Purpose |
| --- | --- | --- |
| Migration governance | `core_schema_migration` | Applied schema-ledger entries and checksums |
| Run evidence | `core_profile`, `core_source_snapshot`, `core_run`, `core_run_sample` | Frozen profile, source, run, and sample-membership evidence |
| Artifact and quality evidence | `core_artifact`, `core_quality_finding` | Artifact hashes/availability and run-scoped findings |
| Native analysis results | Normalized result tables and migration `0007` | Separately governed run-scoped model outcomes; see [`ANALYSIS_PERSISTENCE_V1.md`](ANALYSIS_PERSISTENCE_V1.md) |
| Operational assessment | `core_assessment_artifact`, `core_assessment_revision`, `v_core_assessment_current` | Separate exact-SHA assessment revisions; see [`OPERATIONAL_ASSESSMENT_V1.md`](OPERATIONAL_ASSESSMENT_V1.md) |

**Historical Phase 2B checkpoint:** the seven-table Core foundation had
`0001`/`0002` applied, zero evidence rows, and pipeline persistence disabled.
That snapshot predates the separately authorized Phase 2C fixture import and
the later native-analysis production smoke documented in
[`core_migration`](core_migration/README.md) and
[`ANALYSIS_PERSISTENCE_V1.md`](ANALYSIS_PERSISTENCE_V1.md). Operational
assessment migration `0006` has its own deployment boundary in
[`OPERATIONAL_ASSESSMENT_V1.md`](OPERATIONAL_ASSESSMENT_V1.md). Check the live
Core ledger, account grants, table counts, and writer configuration before
reporting a current deployment state. Core remains downstream; no Core phase
authorizes writes to Erebus or Permission Intel source tables.

### Contributor rules (split database)

- **Primary database:** sample catalog, VT/vendor mirrors, engine verdicts, family/type taxonomy, and other non-permission operational tables.
- **Permission Intel database:** all live `android_permission_*` tables (observations, dictionaries, enrichment).
- **Do not** query `android_permission_*` through primary `execute_query()` only. Use `execute_permission_query()` from `obsidiandroid.database.db_engine`, fully qualified ``schema.table`` in cross-schema SQL, or helpers that delegate to Permission Intel. Brownfield `_legacy_android_permission_*` tables on primary are archive-only and are not a substitute for live PI reads.

Connections are built from `obsidiandroid.database.db_config`. Pooling applies to the primary connection when `OBSIDIAN_DB_ENABLE_POOLING` is enabled; Permission Intel uses a dedicated connection helper (`execute_permission_query` in `obsidiandroid.database.db_engine`).

## Source Refresh and Verification

1. **Cadence:** Confirm the actual upstream Erebus/VirusTotal and Permission
   Intel refresh schedules and receipts. This repository does not establish a
   nightly sync job or a provider request entitlement.
2. **Permission Intel:** Use the approved exact V2 consumer on a gated host.
   Verify its retained source membership and approval; do not infer observations
   from catalog counts or require unsafe legacy reads.
3. **Load ordering:** When an upstream owner loads new detection facts, ensure
   engine metadata and dependent keys are available before analysis.
4. **Verification:** Compare bounded row counts, timestamps, exact-key coverage,
   and the run's frozen source snapshot before interpreting model results. The
   `make audit-runtime-db` command checks source configuration and bounded
   reads; it does not certify a full provider refresh.
5. **Backups:** Follow the owning system's reviewed retention and restore
   policy. No universal seven-day dump period is established by this repo.

## VirusTotal Terms of Use

Access to replicated VirusTotal data must comply with [VirusTotal’s Terms of Service](https://support.virustotal.com/hc/en-us/articles/115002146529-Terms-of-Service). Only authorized personnel may run the sync jobs and distribute derived artefacts. Users should verify that downstream sharing of classification reports is permitted under their agreement.

## Local Development Tips

- Seed a development database by restoring a sanitized snapshot (if your team provides one) or by generating synthetic detections using `scripts/dev/data_fuzzer.py`.
- Prefer `OBSIDIAN_*` environment variables over committing credentials; local overrides can still use `obsidiandroid.database.db_config` defaults for non-secret fields.
- When adding new VirusTotal columns, update both the ORM/select queries and the validation scripts to maintain coverage.

## Related Documentation

- [`architecture.md`](architecture.md) explains how each module consumes the tables listed above.
- [`user_guide.md`](user_guide.md) contains step-by-step configuration instructions for pointing ObsidianDroid at your database instance.
- [`operations_playbook.md`](operations_playbook.md) provides deployment checks and incident triage boundaries; upstream restore procedures remain with their owners.
- [`LABEL_AUTHORITY_SCHEMA_PLAN.md`](LABEL_AUTHORITY_SCHEMA_PLAN.md) defines the proposed
  family/type authority and vendor-label evidence layer for Erebus.
- [`core_migration/phase2_apply_plan.md`](core_migration/phase2_apply_plan.md)
  is retained as historical planning material, not an operational runbook.
