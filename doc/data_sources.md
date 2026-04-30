# Data Sources and Integrations

This guide documents the datasets that ObsidianDroid consumes, how they are synchronized, and the safeguards required to keep the malware labeling pipeline trustworthy. Operators should review this reference before onboarding new feeds or refreshing replicated tables.

## Source of Truth

ObsidianDroid does **not** call live VirusTotal APIs during execution. Instead, it reads from a project-controlled MySQL schema that mirrors the relevant VirusTotal tables alongside derived analytics tables. The database is the authoritative source for:

- Vendor detections and metadata that drive label harmonization.
- Permission manifests extracted from submitted APKs.
- Historical engine performance measurements used in weighting and consensus scoring.

## Database Layout

The current ObsidianDroid pipeline reads from the following tables and views in the
project-controlled MySQL schema:

| Schema Area | Key Tables / Views | Purpose |
| --- | --- | --- |
| Sample catalog | `malware_sample_catalog`, `malware_artifact_hash_registry` | Canonical sample identities, hashes, APK metadata, VT timestamps, package names, and permission counts. |
| Family/type taxonomy | `v_android_apk_family_resolved`, `android_malware_family`, `android_malware_type` | Canonical malware family and type assignments used for cohort building and supervised labels. |
| VirusTotal summaries | `virustotal_sample_scan_summary`, `virustotal_sample_signal_current` | Per-sample detection totals, tags, reputation, and current VT-derived summary fields. |
| VirusTotal verdict matrix | `virustotal_sample_vendor_engine_verdicts` | Wide per-sample vendor verdict table used to build parser inputs and AV feature matrices. |
| Vendor metadata | `virustotal_vendor_engines` | Canonical vendor names plus trusted/active flags used during engine scoring and governance. |
| Android permissions | `android_permission_obs_sample`, `android_permission_enrich_vt_current`, `android_permission_enrich_vt_event` | Observed permission rows and enrichment tables used by permission-trend reporting and feature engineering. |

Connections are managed by `database/db_config.py`. Pooling is configured directly in that module via `DB_ENABLE_POOLING`, `DB_POOL_SIZE`, and `DB_POOL_NAME`.

## Replication & Refresh Cadence

1. **Snapshot frequency:** Pull fresh VirusTotal exports nightly using the upstream sync job documented in the internal ops runbooks.
2. **Ordering guarantees:** Apply engine metadata before loading detection facts to ensure foreign keys resolve.
3. **Verification:** After each load, verify row counts and key coverage for the active ObsidianDroid tables above before running a profile. This repository does not currently ship a dedicated `validate_database_snapshot.py` helper.
4. **Backups:** Retain seven days of dumps for rollback; the `operations_playbook.md` includes recovery instructions.

## VirusTotal Terms of Use

Access to replicated VirusTotal data must comply with [VirusTotal’s Terms of Service](https://support.virustotal.com/hc/en-us/articles/115002146529-Terms-of-Service). Only authorized personnel may run the sync jobs and distribute derived artefacts. Users should verify that downstream sharing of classification reports is permitted under their agreement.

## Local Development Tips

- Seed a development database by restoring the sanitized snapshot in `testing/fixtures/vt_snapshot.sql.gz` (if available) or by generating synthetic detections using `testing/data_fuzzer.py`.
- Override connection settings locally by editing `database/db_config.py` during experimentation.
- When adding new VirusTotal columns, update both the ORM/select queries and the validation scripts to maintain coverage.

## Related Documentation

- [`architecture.md`](architecture.md) explains how each module consumes the tables listed above.
- [`user_guide.md`](user_guide.md) contains step-by-step configuration instructions for pointing ObsidianDroid at your database instance.
- [`operations_playbook.md`](operations_playbook.md) provides incident response and restore workflows for the replication jobs.

