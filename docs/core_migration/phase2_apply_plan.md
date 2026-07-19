# Phase 2 approval package: Core evidence foundation

## Scope and stop condition

Phase 2 is separately approved work. It may apply
`database/core_migrations/0001_core_evidence_foundation.sql` only after a
successful, receipted restore rehearsal of the July 19 Erebus and Permission
Intel backups. It must not delete, rename, or update any source record.

## Required accounts and grants

```sql
-- Names are requirements, not commands to run in Phase 1.
-- obsidiandroid_source_reader: SELECT on erebus_threat_intel_prod.*
-- obsidiandroid_permission_reader: SELECT on android_permission_intel.*
-- obsidiandroid_core_writer: SELECT, INSERT, UPDATE, DELETE on obsidiandroid_core_prod.*
-- No source-reader account receives CREATE, INSERT, UPDATE, DELETE, or DROP.
-- No core-writer account receives any privilege on the two source schemas.
```

## Ordered application steps

1. Confirm `obsidiandroid_core_prod` is empty and the recovery-verification
   receipt is valid for the source backup IDs.
2. Connect as the dedicated core writer with a UTC session and apply the one
   reviewed DDL file.
3. Insert one successful `core_schema_migration` row with the DDL SHA-256,
   application commit, and UTC application timestamp.
4. Run the dry-run planner for `20260718T032717Z__a8cf01`; compare its plan hash
   and expected rows against the Phase 1 preview.
5. Copy the first-wave source tables only: `analysis_run`, `analysis_snapshot`,
   `analysis_snapshot_sample`, `analysis_artifact`, and
   `snapshot_label_conflict`.
6. Validate source/destination counts and per-run keys. Do not switch the
   active warehouse writer in the same change window.

## Expected July 18 fixture rows

The generated Phase 1 preview is
`docs/core_migration/inventory/july18_fixture_migration_preview.json` and is
deliberately uncommitted. At Phase 1 capture it proposes one profile, one run,
one snapshot, 9,716 sample-membership records, 57 artifact records, and zero
snapshot-conflict findings. It remains `current-corpus diagnostic` and
`NOT_APPLICABLE` for publication.

## Validation queries

```sql
SELECT COUNT(*) FROM core_run WHERE run_id = :run_id;
SELECT COUNT(*) FROM core_run_sample WHERE run_id = :run_id;
SELECT COUNT(*) FROM core_artifact WHERE run_id = :run_id;
SELECT COUNT(*) FROM core_quality_finding WHERE run_id = :run_id;
SELECT COUNT(*) FROM core_schema_migration WHERE execution_status = 'applied';
```

Compare each value with the dry-run plan and source query counts. Verify every
fixture artifact still has the Phase 1 path/hash status; availability must not
be inferred from metadata alone.

## Expected writes

- One reviewed DDL migration in `obsidiandroid_core_prod` only.
- One migration-ledger row.
- Destination rows for the approved first-wave runs.
- A dated migration receipt and validation report under the configured
  artifact root.

No writes are permitted to `erebus_threat_intel_prod` or
`android_permission_intel`. No source artifact path is rewritten, and no
artifact file is copied in the first wave.

## Rollback

If validation fails before cutover, delete only destination rows keyed by the
Phase 2 import receipt/run IDs, in child-to-parent order, inside the core
database transaction. Preserve the source tables and the failed receipt. Do
not drop the core schema or modify the source databases as rollback.

## Remaining blockers

- A restore rehearsal and separate recovery-verification receipt.
- Review of the seven uncommitted Phase 1 inventories.
- Dedicated database accounts/grants.
- Review of the DDL and planner output.
- Explicit approval of the exact Phase 2 transaction boundaries.
