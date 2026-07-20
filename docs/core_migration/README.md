# ObsidianDroid Core migration

This directory contains the controlled transition from the current Erebus and
Permission Intel source schemas to a separate ObsidianDroid-owned evidence
database. It is not a migration runner and it does not authorize database
writes.

## Phase 1: closed historical foundation

Phase 1 produced the design, validation, and evidence-preservation material
that was later reviewed before Phase 2B provisioning:

- `database/core_migrations/0001_core_evidence_foundation.sql` is the reviewed
  seven-table foundation; it was preserved as un-applied Phase 1 design and is
  now recorded as applied in the production Core migration ledger.
- `scripts/core_migration/dry_run_evidence_migration.py` can build a
  deterministic plan from approved read-only source evidence; it contains no
  DDL or DML.
- `scripts/core_migration/generate_phase1_inventory.py` writes local source and
  artifact inventories. Its reports live under `inventory/`, are ignored by
  Git, and must be reviewed locally rather than treated as versioned source.
  The exact report schema, evidence rules, and synthetic failure boundary are
  documented in [phase1_closeout_contract.md](phase1_closeout_contract.md).
- `make check-phase1-closeout` performs an offline-only historical-contract
  check. It confirms that Core persistence is disabled, the reviewed DDL has
  the expected evidence tables, report contracts and writer coverage are
  complete, report checksums exist, and the July 18 fixture preview remains a
  nonpublication dry run with its expected row plan. It does not open a
  database connection.

An `OK` result preserves the Phase 1 contract; it does **not** authorize a
fixture import, pipeline routing change, source-schema change, or benchmark.

## Phase 2B: schema, provisioning, and grant separation

Phase 2B added the reviewed additive `0002` contract migration, a fail-closed
Core-only migration executor, deterministic mapping planner, synthetic
disposable validation, production provisioning, and narrow local service
accounts. `obsidiandroid_core_prod` now has exactly seven Core tables and two
applied migration rows, but zero evidence rows. Core persistence remains
disabled; no pipeline routing, dual write, or July 18 fixture import has
occurred. The durable design is in
[phase2b_core_contract.md](phase2b_core_contract.md), the mapping is in
[phase2b_source_mapping.md](phase2b_source_mapping.md), and the historical
Phase 2 plan is not an operational runbook.

Phase 2C remains a separately authorized controlled fixture import. Its
[review gate](phase2c_controlled_import_review.md) binds any future production
write to one reviewed source-extract package, deterministic plan, exact
migration bytes, preflight audit, target server, writer identity, and a
single-use authorization-consumption receipt. No source extract, authorization,
or fixture import has yet been created or executed. Phase 2D remains separately
authorized pipeline integration.

When separately authorized, only
`scripts/core_migration/create_phase2c_source_extract.py` may create the first
fixture package. It is locked to `20260718T032717Z__a8cf01`, requires the
dedicated `obsidiandroid_erebus_reader` credential and an explicit read-only
acknowledgement, uses a single consistent read-only transaction, writes outside
the repository, and never opens Core. The older
`dry_run_evidence_migration.py` remains Phase 1 historical planning material;
it is not the Phase 2C extractor.

`scripts/core_migration/build_phase2c_import_plan.py` is the next offline-only
step. It verifies every compressed extract and canonical payload hash before it
maps the reviewed rows into a plan. It binds that plan to the extract-manifest
hash, the local repository commit, both exact Core migration checksums, expected
counts, and post-import row/key reconciliation hashes. It has no database
connection code and cannot execute an import. Plan creation and production
execution both require a clean checkout at the reviewed commit; a Git commit
identifier alone does not authorize uncommitted code.

The final production-only boundary is
`scripts/core_migration/execute_phase2c_import.py`. It cannot build an extract
or plan and is not called by the normal pipeline. When separately authorized,
it accepts only private external reviewed files, the dedicated Core-writer
option file, a new external execution-receipt path, and an exact confirmation
token. It consumes the single-use authorization before opening Core, then the
library importer verifies the reviewed preflights, clean commit, target-server
attestation, and writer identity before any transaction begins.

After a committed import, use
`scripts/core_migration/verify_phase2c_import.py` with the Core auditor
credential and the same private plan. It can only read the six Core evidence
tables, requires the `obsidiandroid_core_auditor@localhost` identity, and
records a plan-bound count/key/row-hash reconciliation receipt outside Git.

Before a Phase 2C authorization is issued, run the read-only Core audit and
preserve its complete JSON result. The authorization binds the self-verifying
audit hash and the audit's MariaDB server attestation (hostname, port,
server-id, version, and version comment). The importer rechecks those values
immediately before writing. This is a deterministic MariaDB attestation, not a
claim that the server exposes MySQL's unsupported `@@server_uuid` variable.
The audit recognizes the separately approved normal
`obsidiandroid_pipeline_reader` account as a runtime reader, while continuing
to require the four Phase 2B/Core identities and reject any unreviewed
`obsidiandroid_*` account. The normal reader is not a Core identity and must
never receive Core privileges.

Before the first real Core evidence import, create and rehearse a Core recovery
package with `scripts/core_migration/core_backup_rehearsal.py`. It requires a
private MariaDB option file, stores a checksum-bound dump package outside the
repository, and restores only to a new `od_core_restore_*` disposable schema
when `--apply` is explicitly supplied. A failed creation or rehearsal writes a
credential-free, non-overwriting failure receipt beside the attempted external
package; its exception type is preserved but its message is intentionally not
recorded. Do not treat a created dump as recovery evidence until its disposable
restore reports `PASS`.

Before moving to another workstation or database host, run
`make preflight-migration-host OPTION_FILE=<private.cnf> MODE=local|remote`.
It is read-only and records the supported Python range, required MariaDB
clients, MariaDB version/family, identifier behavior, scheduler state, and
transport policy. A remote deployment is blocked unless TLS is available and
required and `local_infile` is disabled; do not weaken that gate to accommodate
an unprepared remote server.

For Phase 2C, the passing host-preflight JSON hash is part of the one-time
authorization alongside the Core audit hash. The importer rejects a missing,
changed, or blocked host report before it consumes the authorization or opens
the Core writer connection.

The service-account provisioner is single-use: it refuses existing account or
receipt paths, creates accounts and grants before writing local credential
references, and emits a credential-free failure receipt if MariaDB leaves a
partial DDL effect. It never performs automatic cleanup of a partial account
operation; that requires review of the preserved receipt and a targeted
administrator action.

## Earlier Phase 2 planning material

[phase2_apply_plan.md](phase2_apply_plan.md) is retained only as historical
context. Use the current Phase 2B contract and provisioning runbook instead.
