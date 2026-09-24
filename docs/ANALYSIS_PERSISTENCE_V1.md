# Native analytical persistence V1

Analytical predictions and governed assessments are separate records. This writer never creates or revises an assessment. Existing exploratory analysis remains the default; Full pipeline offers an explicit persistence choice.

```bash
./run.sh analysis history
./run.sh analysis show --run-id RUN_ID
./run.sh analysis predictions --run-id RUN_ID
./run.sh analysis verify --run-id RUN_ID
./run.sh analysis export --run-id RUN_ID --output /absolute/new-export-directory
./run.sh analysis run --profile android_malware_all_current --persist --plan-only
./run.sh analysis run --profile android_malware_all_current --persist
```

The last command trains the configured models and writes a new run. The plan command performs read-only profile/schema/receipt/actor inspection; it does not claim that source inputs or models have already executed successfully. The expensive full-corpus run was not part of the bounded production smoke.

The local writer configuration is `~/.config/obsidiandroid/analysis-writer.cnf` (0600). Inspection commands accept alternate option files and explicit disposable targets. Pipeline execution uses the configured production writer; alternate execution targets are rejected rather than silently ignored.

## Contract and boundaries

`analysis_persistence.service.AnalysisStore` owns transactions, independent of the menu. A UUID identifies each run. Begin commits a RUNNING header; finalization commits exact membership, splits, model identities, every SHA outcome, metrics, confusion cells and artifact references atomically, then marks it completed (API `SUCCEEDED`). Failure/cancellation records retain sanitized stage/type and any captured membership/reference context. An abrupt process death can leave RUNNING; it cannot fabricate success. Investigate and explicitly use `fail_run` or resume the exact stored input; do not automatically delete or rewrite unfinished runs.

A plan is read-only and unpersisted; the existing schema also supports `planned`. Completed/failed/cancelled native records are immutable. Re-finalizing the same UUID and identical result returns `EXACT_REPLAY`. A deliberate repetition uses a new UUID and records `replay_of_run_id` when scientific inputs match. Concurrent finalization of the same UUID is serialized by a row lock.

The cohort boundary is the profile SQL loader's returned rows before Python preparation/alignment. Pre-query SQL exclusions are outside this cohort. Every captured SHA is retained, including later exclusions. SHA-256 is the canonical Obsidian artifact identity (`core_assessment_artifact` also uses SHA as its primary key); `core_run_sample.source_sample_id` is separately namespaced `erebus_sample_id`. Numeric `artifact_id` in the first smoke's input metadata is a legacy source-ID alias, not an Obsidian numeric primary key. New adapter payloads name the two identities explicitly.

Per-model split contracts retain exact train/test/excluded/inference membership, labels, seeds, algorithm and digest. Feature contracts retain actual ordered model columns and input digests; models can have different feature schemas. Family, type and variant are explicit dimensions. NaN/Infinity estimator parameters are represented as tagged JSON values; non-finite scores and metrics remain invalid. Predictions do not imply governed label support. The adapter currently rejects repeated model keys, such as ablation executions in one run, instead of overwriting an earlier model.

Completed model artifacts, feature snapshots and cohort JSON are registered by relative path, SHA and byte size. Export reconstructs normalized JSON/TSV records from MariaDB and rechecks files, reporting missing/changed files without hiding durable database results. Database backup preserves references, not large external model binaries; retain the registered artifact root separately. Export does not deserialize model files.

`analysis verify --run-id RUN_ID` reads the native run and hashes its registered files without creating an export directory or deserializing models. It reports each artifact role/path as verified, changed, missing/unsafe, or root unavailable. Exit code 2 means one or more registered artifacts could not be verified (including optional artifacts); an empty registry reports `no_registered_artifacts`, not a successful file verification. Missing artifact roots do not prevent export of the durable database records. Invalid CLI requests are rejected before connection setup.

For new pipeline captures, an advertised model metadata sidecar is copied and checksummed alongside the estimator and feature input. A missing or symlinked advertised sidecar fails capture instead of silently dropping the label metadata. Models without an advertised sidecar remain supported with no metadata artifact reference. This retains existing label/class metadata; it does not establish an active-model registry or a complete validated inference/preprocessing bundle, and it does not backfill older runs.

## Database deployment and recovery

Reuse `core_run`, `core_run_sample`, `core_profile`, `core_source_snapshot`, `core_artifact`, and the existing normalized result tables. Migration 0005 removes legacy `core_` prefixes from result tables; 0007 adds native identity/status fields and 32 immutability triggers. No duplicate analytical schema and no Erebus warehouse writer are introduced.

Migration-created triggers require a durable definer. Never drop that account during teardown: lock it and reduce its privileges to the table-level SELECT/TRIGGER requirements. Validate definer existence and grants as well as table/index/FK/trigger-body shape. The production pilot exposed and recovered a missing-definer error; its failed transaction and same-UUID recovery are retained in the audit packet.

The writer has scoped SELECT/INSERT rights and only the header UPDATE columns needed for lifecycle/finalization. It has no DDL, assessment mutations, or Erebus/Permission Intel writes. A source snapshot is appended when runtime inputs resolve the initial pending plan, preserving the original planning record.

Validation evidence and the one production smoke are in:
`/home/systemadmin/Documents/ObsidianDroid_Audits/ANALYSIS_PERSISTENCE_V1_20260921/`.
