# Phase 2B production provisioning runbook — approval required

This is an execution runbook for a separately approved change window only. It
creates the seven empty Core tables and stops. It does **not** import the July
18 fixture, enable persistence, switch a writer, read/write source evidence,
or run ObsidianDroid.

## Immutable inputs and prerequisites

1. Approval names target `obsidiandroid_core_prod`, the window owner, the Core
   migrator identity, and this exact migration pair.
2. Verify the target is exactly `obsidiandroid_core_prod`, not any Erebus,
   Permission Intel, restore, rehearsal, or disposable schema.
3. Verify it has 0 tables, views, triggers, routines, and events; stop if not.
4. Verify source readers, Core migrator, Core writer, and Core auditor are
   separate accounts under the grant plan. No grants are created by this
   runbook; passwords never appear in a command or receipt.
5. Verify persistence remains disabled and no pipeline routing targets Core.
6. Verify the repository commit, clean/approved worktree state, Phase 1
   package, Phase 2B contract, and latest disposable receipt are preserved.

```text
0001 fd65d0106b50484da3ca802f8a2b98649f9bac06993989c5602f09d30c0badae
0002 076fefdc613e9f359f03c2156027009f0950df33b4e049cd501c523dcb4c9b21
```

## Execution sequence

1. Run the dedicated Core migration executor in non-dry-run mode with an
   explicit production authorization flag and the Core-migrator connection.
   It must reject any selected schema other than the approved target.
2. Apply `0001`; inspect that exactly one `core_schema_migration` record has
   version `0001`, its exact SHA, and `execution_status='applied'`.
3. Apply final `0002`; inspect the second ledger row, its exact final SHA,
   executor identity, MariaDB version, duration, and receipt ID.
4. Stop. Do not execute any importer or application pipeline command.

MariaDB DDL can implicitly commit. A failure can leave partial DDL despite a
transaction rollback. The executor must never ledger a failed migration as
`applied`; preserve its receipt, inspect `information_schema` object/column/
constraint state, and obtain a new reviewed remediation plan. Do not promise
or attempt a blind transactional DDL rollback.

## Required post-DDL validation

Run as the Core auditor, with no DML:

```sql
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'obsidiandroid_core_prod'
ORDER BY TABLE_NAME;

SELECT migration_version, migration_checksum, execution_status
FROM obsidiandroid_core_prod.core_schema_migration
ORDER BY migration_version;

SELECT TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE TABLE_SCHEMA = 'obsidiandroid_core_prod'
ORDER BY TABLE_NAME, CONSTRAINT_NAME;

SELECT COUNT(*) AS cross_schema_foreign_keys
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = 'obsidiandroid_core_prod'
  AND UNIQUE_CONSTRAINT_SCHEMA <> 'obsidiandroid_core_prod';

SELECT
  (SELECT COUNT(*) FROM information_schema.VIEWS WHERE TABLE_SCHEMA = 'obsidiandroid_core_prod') AS views,
  (SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = 'obsidiandroid_core_prod') AS triggers,
  (SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA = 'obsidiandroid_core_prod') AS routines,
  (SELECT COUNT(*) FROM information_schema.EVENTS WHERE EVENT_SCHEMA = 'obsidiandroid_core_prod') AS events;
```

Expected result: exactly seven InnoDB `utf8mb4_unicode_ci` tables, two applied
migration rows, all reviewed keys/checks/FKs, zero cross-schema FKs, and zero
views/triggers/routines/events. Query every Core evidence table and require a
zero row count. Reconfirm persistence is disabled, source schemas were not
written, and no application route changed.

## Abort, receipt, and recovery

Abort before DDL for an identity mismatch, nonempty target, checksum mismatch,
missing approved account separation, disabled preservation evidence, or route/
persistence change. Abort after DDL for an unexpected object, missing ledger
row, wrong checksum, source-schema activity, or nonempty evidence table.

The provisioning receipt records: approval ID; target and server version;
repository commit; executor identity; both migration names/hashes/durations;
pre/post object inventory; constraint/index/FK validation; zero-row evidence
checks; persistence and route checks; source-write checks; timestamps; and
credential-free error details. A failed/partial DDL receipt is preserved and
blocks import/cutover until reviewed recovery work is approved.
