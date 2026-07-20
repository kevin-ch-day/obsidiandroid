# Phase 2B approved-source to Core mapping matrix (v1)

`erebus_threat_intel_prod` is read-only. The matrix lists every column seen in
the approved source surfaces; absent Core fields are not invented. Source-row
hash means SHA-256 of canonical JSON for the complete source row. Child tables
use `run_id`; samples use SHA-256 or `erebus_sample_id:<id>` as a deterministic
fallback key. Import order is run parent, snapshot, then run, samples,
artifacts and findings. Any nullability/rejection below preserves absence; it
never becomes zero, false, complete, or validated.

| Source surface / column | type, nullability | target / classification | transformation, rejection, risk |
|---|---|---|---|
| `analysis_run.run_id` | varchar(64), no | `core_run.run_id`; mapped_directly | natural identity; required; duplicate with different complete-row hash rejects. |
| `created_at_utc` | datetime, no | `core_run.run_started_at_utc`; mapped_directly | source observation/start proxy only; no completion inferred. |
| `profile_id` | varchar(64), no | `core_profile.profile_id`, `core_run.profile_id`; mapped_directly | parent inserted first; profile contract unavailable. |
| `git_commit` | varchar(64), yes | `core_run.application_commit`; mapped_directly | null retained. |
| `selection_rule_version` | varchar(128), no | `core_run.metadata_json.selection_rule_version`; retained_in_structured_metadata | original version string; must equal the snapshot value when a snapshot exists. |
| `snapshot_sha256_hash` | char(64), no | `core_source_snapshot.cohort_checksum`, `core_run.configuration_hash`; mapped_directly | hash semantics retained as source declares. |
| `snapshot_row_count` | int, no | `core_source_snapshot.source_row_counts_json`; retained_in_structured_metadata | count mismatch with supplied samples rejects controlled import. |
| `vendor_constrained_run_flag` | tinyint, no | `core_run.metadata_json`; retained_in_structured_metadata | not promoted to publication/quality claim. |
| `selected_vendor_count` | int, no | `core_run.metadata_json`; retained_in_structured_metadata | no missing count inferred. |
| `included_vendor_count` | int, no | `core_run.metadata_json`; retained_in_structured_metadata | same. |
| `excluded_vendor_count` | int, no | `core_run.metadata_json`; retained_in_structured_metadata | same. |
| `notes` | text, yes | `core_run.metadata_json`; retained_in_structured_metadata | redaction review required before production import. |
| `analysis_snapshot.run_id` | varchar(64), no | parent linkage; mapped_directly | must equal parent run. |
| `extracted_at_utc` | datetime, no | `core_source_snapshot.extracted_at_utc`; mapped_directly | snapshot observation time. |
| `selection_rule_version` | varchar(128), no | `core_source_snapshot.source_query_contract_version`; mapped_directly | source version string. It also participates in canonical `core-approved-source-query-contract-v1`, whose SHA-256 is stored in `source_query_contract_hash`. |
| `snapshot_sha256_hash` | char(64), no | `core_source_snapshot.cohort_checksum`; mapped_directly | stable snapshot evidence. |
| `snapshot_row_count` | int, no | `core_source_snapshot.source_row_counts_json`; retained_in_structured_metadata | reconciliation expectation. |
| `selected_vendor_count` | int, no | `core_source_snapshot.source_row_counts_json`; retained_in_structured_metadata | stored with snapshot evidence. |
| `included_vendor_count` | int, no | `core_source_snapshot.source_row_counts_json`; retained_in_structured_metadata | stored with snapshot evidence. |
| `excluded_vendor_count` | int, no | `core_source_snapshot.source_row_counts_json`; retained_in_structured_metadata | stored with snapshot evidence. |
| `vendor_constrained_run_flag` | tinyint, no | `core_source_snapshot.source_catalogs_json`; retained_in_structured_metadata | source semantics retained. |
| `analysis_snapshot_sample.run_id` | varchar(64), no | `core_run_sample.run_id`; mapped_directly | child must match run. |
| `sha256` | char(64), no | `core_run_sample.sha256`, `sample_key`; mapped_directly | preferred natural sample identity. |
| `sample_id` | bigint unsigned, yes | `core_run_sample.source_sample_id`; mapped_directly | namespace is explicitly `erebus_sample_id`; no FK. |
| `family_id` | int, yes | none; intentionally_not_imported_but_hash_covered | Core preserves `family_canonical` as the observed historic label and must not copy an Erebus taxonomy ID or infer current authority. The complete-row hash detects change but does **not** reproduce this value. |
| `family_canonical` | varchar(255), yes | `core_run_sample.observed_family`; mapped_directly | historical observed value, authority `unknown`. |
| `type_slug` | varchar(64), yes | `core_run_sample.observed_type`; mapped_directly | historical observed value, authority `unknown`. |
| `extracted_at_utc` | datetime, no | none; intentionally_not_imported_but_hash_covered | omitted because Core v1 has no per-membership observation-time field. The complete-row hash detects change but does **not** preserve the timestamp. |
| `feature_hash` | char(64), yes | `core_run_sample.record_checksum`; mapped_directly | feature content unavailable; null retained. |
| `analysis_artifact.run_id` | varchar(64), no | `core_artifact.run_id`; mapped_directly | parent run required. |
| `artifact_key` | varchar(128), no | `core_artifact.artifact_role`; mapped_directly | per-run natural identity; duplicate rejects. |
| `artifact_path` | text, no | `core_artifact.legacy_source_path`; mapped_directly | metadata only; `.latest` becomes mutable pointer only; no file copy. |
| `artifact_sha256` | char(64), yes | `core_artifact.sha256`, `expected_sha256`; mapped_directly | observed hash remains null until actual validation. |
| `created_at_utc` | datetime, no | `core_artifact.created_at_utc`; mapped_directly | source creation observation. |
| `snapshot_label_conflict.run_id` | varchar(64), no | `core_quality_finding.run_id`; mapped_directly | parent required. |
| `sha256` | char(64), no | `core_quality_finding.sample_key`; mapped_directly | no sample FK because a finding can outlive membership import. |
| `conflict_type` | varchar(64), no | `core_quality_finding.finding_code`; mapped_directly | mapped kind is `source_conflict`; no automatic repair. |
| `observed_values` | text, no | `core_quality_finding.observed_values_json`; retained_in_structured_metadata | source text retained as observed evidence; selected value remains null/open. |
| `created_at_utc` | datetime, no | `core_quality_finding.created_at_utc`; mapped_directly | detection time, not review time. |

All five surfaces also map their complete canonical row into the applicable
`source_record_hash`; this is a `mapped_with_transformation` provenance field.
It establishes equality/change detection only; it is never described as
retaining an omitted source value.
No approved source column is `unavailable` or `unresolved` at this mapping
stage. The following Core data are intentionally not imported because sources
do not provide them: profile version/contract, source schema hash, taxonomy or
permission snapshots, split assignments, label authority, observed artifact
hash/size, archive recovery, resolution authority, and review timestamp.
