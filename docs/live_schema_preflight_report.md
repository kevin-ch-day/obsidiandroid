# Live Schema Preflight — Frozen Android AV A/B/C Provider

**Scope:** read-only source-contract inspection only. No cohort was locked, no split or feature contract was fitted, no model was trained, and no held-out evaluation was authorized or run.

## Safety record

| Item | Observed value |
|---|---|
| Primary database | `erebus_threat_intel_prod` |
| Permission database | `android_permission_intel` |
| Server/source identity | Redacted; configured application database source |
| Database version | MariaDB `10.11.18` |
| Server UTC at inspection | 2026-07-16 23:12:59 (primary); 23:13:00 (Permission Intel) |
| Connection mode | Direct MySQL Connector/Python; `autocommit=False` |
| Isolation level | `REPEATABLE-READ` |
| Read-only transaction | `SET TRANSACTION READ ONLY` accepted; `START TRANSACTION WITH CONSISTENT SNAPSHOT` started on both inspected schemas |

Only `SELECT` and transaction-control statements were issued. No DDL, DML, imports, refreshes, or stored routines were executed.

## VirusTotal verdict source

`virustotal_sample_vendor_engine_verdicts` is a **base table** in wide form. It has 28,491 rows and 28,491 distinct `sample_id` values. Its primary key is `sample_id`, with a foreign key to `malware_sample_catalog.sample_id`. The table holds 102 engine-result text columns plus `updated_at`.

It does **not** expose `report_id`, `analysis_id`, `scan_id`, retrieval batch, report timestamp, retrieval timestamp, created timestamp, or any other report-version identity. The only matching audit/ordering field is `updated_at`, which is an `ON UPDATE CURRENT_TIMESTAMP` field for the complete wide row. It may order the current stored row, but it cannot identify a VirusTotal report or establish an immutable historical snapshot.

Answers to the report-identity questions:

1. No verified coherent report-level identity is retained.
2. A complete *current* wide row can be read without per-engine mixing, but a complete report snapshot cannot be selected or reproduced across historical scans.
3. Yes, one wide row contains the stored engine matrix for one sample; no evidence establishes that it represents a named VT report/analysis.
4. Historical report versions are not retained in this table: the primary key is only `sample_id` and `updated_at` is mutable.
5. No field identifies report identity.
6. `updated_at` is audit/ordering metadata only.
7. It is one mutable row-level timestamp, not a report identity.
8. No: the provider cannot retrieve one immutable report snapshot per canonical sample.

**Coherent-report classification:** `MUTABLE_LATEST_ONLY`.

## Engine metadata

`virustotal_vendor_engines` is a base table with primary key `vendor_engine_id` and unique `vendor_key`. It provides `vendor_key`, `vendor_name`, `is_engine_active`, `is_trusted_vendor`, and mutable `updated_at`. No database alias relation or historical effective-status interval was found.

Therefore active/trusted means **status in the current frozen metadata snapshot**, not status at AV-observation time. A future provider may preserve the current metadata extract, but must not imply historical temporal alignment.

## Permission observations and knowledge

`android_permission_obs_sample` is a base table with primary key `obs_id` and unique `(sample_id, permission_string)`. It exposes raw `permission_string`, generated nullable `permission_string_norm`, `classification`, `bucket`, `vendor_id`, `observed_at_utc`, `source`, and `run_id`.

The read-only probe found no currently blank normalized values and no duplicate `(sample_id, permission_string)` groups. The runtime per-row fallback from blank normalized token to raw token remains required as a defensive contract for future rows. `run_id` exists, but uniqueness is not versioned by `run_id`; the table cannot provide multiple immutable extraction snapshots for the same sample/permission pair.

Knowledge tables are current-state base tables: `android_permission_dict_aosp`, `android_permission_dict_oem`, `android_permission_dict_unknown`, `android_permission_meta_oem_vendor`, and `android_permission_enrich_vt_current`. They expose authority/protection or vendor fields where applicable, but their `record_updated_at_utc` fields demonstrate mutable current-state behavior rather than a globally versioned knowledge snapshot.

## Cohort, Android metadata, labels, and taxonomy

`malware_sample_catalog` provides unique `sample_id` and `sha256`, Android package, minimum/target SDK, first-submission timestamp, and mutable record timestamps. `v_android_sample_family_type_authority` provides family/type authority fields and filters Android APKs, but the read-only duplicate probe found at least one duplicate `sample_id`. The same is true for `v_android_apk_family_resolved`.

`android_malware_family` has primary key `family_id` and unique `family_slug`; it records active status and current timestamps. Alias tables preserve an alias-to-family relation, but neither inspected alias uniqueness constraint makes `alias_name`/`alias_token` globally unique across all canonical families. A future provider therefore needs an explicit deterministic alias-conflict rejection rule. Malware type is available as governance/evaluation metadata through `android_malware_type` and must remain absent from feature frames.

## Temporal classification and transaction limits

| Source | Classification | Reason |
|---|---|---|
| Cohort and labels | `MUTABLE_LATEST_STATE` | catalog and authority views include current mutable sources |
| Android SDK metadata | `MUTABLE_LATEST_STATE` | catalog `record_updated_at_utc` is mutable |
| Permission observations | `MUTABLE_LATEST_STATE` | one current row per sample/permission; no versioned observation history |
| Permission knowledge | `MUTABLE_LATEST_STATE` | dictionary/enrichment tables have current mutable rows |
| VT reports | `MUTABLE_LATEST_STATE` | one wide row per sample, mutable `updated_at`, no report identity |
| Engine metadata | `MUTABLE_LATEST_STATE` | current status plus mutable `updated_at` |
| Taxonomy and aliases | `MUTABLE_LATEST_STATE` | active/current authority tables with mutable timestamps |

One consistent read-only transaction works within each inspected schema. This preflight did not establish one transaction spanning the application’s separate primary and Permission Intel connections, so a future permitted extraction must materialize all required run-local source extracts immediately and record per-extract hashes. That would not repair the missing VT report identity.

## Decision

The exact provider decision is **`LIVE_PROVIDER_BLOCKED_MUTABLE_LATEST_ONLY`**. `DatabaseFrozenBenchmarkSourceProvider` must remain fail-closed with `LIVE_SCHEMA_UNVERIFIED`.

Readiness after this preflight:

| Activity | Status |
|---|---|
| Provider implementation | Blocked |
| Real cohort lock | Not authorized |
| Real split lock | Not authorized |
| Feature-contract fitting | Not authorized |
| Held-out authorization | Not authorized |
