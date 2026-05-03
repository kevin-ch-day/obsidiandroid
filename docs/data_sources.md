# Data Sources and Integrations

This guide documents the datasets that ObsidianDroid consumes, how they are synchronized, and the safeguards required to keep the malware labeling pipeline trustworthy. Operators should review this reference before onboarding new feeds or refreshing replicated tables.

## Source of Truth

ObsidianDroid does **not** call live VirusTotal APIs during execution. Instead, it reads from project-controlled MySQL schemas. **Sample catalog, VirusTotal mirrors, and vendor verdicts** live in the primary Erebus database. **Android permission intelligence** (`android_permission_*` tables) lives in the separate Permission Intel database (see below). Together they are the authoritative source for:

- Vendor detections and metadata that drive label harmonization.
- Permission observations and enrichment used for permission features and permission-trend reporting.
- Historical engine performance measurements used in weighting and consensus scoring.

## Database Layout (split model)

ObsidianDroid uses two logical databases on the same MySQL/MariaDB instance in typical deployments. Configure schema names with `OBSIDIAN_DB_NAME` (primary) and `OBSIDIAN_PERMISSION_INTEL_DB_NAME` (Permission Intel); see `database/db_config.py`.

### Primary Erebus database (`OBSIDIAN_DB_NAME`, default `erebus_threat_intel_prod`)

| Schema area | Key tables / views | Purpose |
| --- | --- | --- |
| Sample catalog | `malware_sample_catalog`, `malware_artifact_hash_registry` | Canonical sample identities, hashes, APK metadata, VT timestamps, package names, and catalog permission counts. |
| Family/type taxonomy | `v_android_apk_family_resolved`, `android_malware_family`, `android_malware_type` | Canonical malware family and type assignments used for cohort building and supervised labels. |
| VirusTotal summaries | `virustotal_sample_scan_summary`, `virustotal_sample_signal_current` | Per-sample detection totals, tags, reputation, and current VT-derived summary fields. |
| VirusTotal verdict matrix | `virustotal_sample_vendor_engine_verdicts` | Wide per-sample vendor verdict table used to build parser inputs and AV feature matrices. |
| Vendor metadata | `virustotal_vendor_engines` | Canonical vendor names plus trusted/active flags used during engine scoring and governance. |

### Permission Intel database (`OBSIDIAN_PERMISSION_INTEL_DB_NAME`, default `android_permission_intel`)

| Schema area | Key tables | Purpose |
| --- | --- | --- |
| Android permissions | `android_permission_obs_sample`, `android_permission_dict_aosp`, `android_permission_dict_oem`, `android_permission_dict_unknown`, `android_permission_meta_oem_vendor`, `android_permission_enrich_vt_current`, `android_permission_enrich_vt_event` | Observed permission rows, dictionaries, OEM metadata, and enrichment used by permission-trend reporting and ML permission features. |

On `android_permission_obs_sample`, the observation timestamp column is **`observed_at_utc`** (not `record_created_at_utc`). Diagnostics and SQL should use that name when filtering or ordering PI observation rows.

Cross-schema reporting joins (for example banking trojan permission extracts) qualify both databases in SQL (e.g. ``primary.malware_sample_catalog`` joined to ``android_permission_intel.android_permission_obs_sample``). ObsidianDroid does **not** assume live `android_permission_*` tables exist in the primary database.

### Contributor rules (split database)

- **Primary database:** sample catalog, VT/vendor mirrors, engine verdicts, family/type taxonomy, and other non-permission operational tables.
- **Permission Intel database:** all live `android_permission_*` tables (observations, dictionaries, enrichment).
- **Do not** query `android_permission_*` through primary `execute_query()` only. Use `execute_permission_query()` from `database/db_engine.py`, fully qualified ``schema.table`` in cross-schema SQL, or helpers that delegate to Permission Intel. Brownfield `_legacy_android_permission_*` tables on primary are archive-only and are not a substitute for live PI reads.

Connections are built from `database/db_config.py`. Pooling applies to the primary connection when `OBSIDIAN_DB_ENABLE_POOLING` is enabled; Permission Intel uses a dedicated connection helper (`execute_permission_query` in `database/db_engine.py`).

## Replication & Refresh Cadence

1. **Snapshot frequency:** Pull fresh VirusTotal exports nightly using the upstream sync job documented in the internal ops runbooks.
2. **Permission Intel:** Erebus mines and stores permission intelligence; the Permission Intel schema is the live consumer-facing source for ObsidianDroid permission paths.
3. **Ordering guarantees:** Apply engine metadata before loading detection facts to ensure foreign keys resolve.
4. **Verification:** After each load, verify row counts and key coverage for the active ObsidianDroid tables above before running a profile. This repository does not currently ship a dedicated `validate_database_snapshot.py` helper.
5. **Backups:** Retain seven days of dumps for rollback; the `operations_playbook.md` includes recovery instructions.

## VirusTotal Terms of Use

Access to replicated VirusTotal data must comply with [VirusTotal’s Terms of Service](https://support.virustotal.com/hc/en-us/articles/115002146529-Terms-of-Service). Only authorized personnel may run the sync jobs and distribute derived artefacts. Users should verify that downstream sharing of classification reports is permitted under their agreement.

## Local Development Tips

- Seed a development database by restoring the sanitized snapshot in `testing/fixtures/vt_snapshot.sql.gz` (if available) or by generating synthetic detections using `testing/data_fuzzer.py`.
- Prefer `OBSIDIAN_*` environment variables over committing credentials; local overrides can still use `database/db_config.py` defaults for non-secret fields.
- When adding new VirusTotal columns, update both the ORM/select queries and the validation scripts to maintain coverage.

## Related Documentation

- [`architecture.md`](architecture.md) explains how each module consumes the tables listed above.
- [`user_guide.md`](user_guide.md) contains step-by-step configuration instructions for pointing ObsidianDroid at your database instance.
- [`operations_playbook.md`](operations_playbook.md) provides incident response and restore workflows for the replication jobs.
