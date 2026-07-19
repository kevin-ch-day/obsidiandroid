# ObsidianDroid Core migration

This directory contains the controlled transition from the current Erebus and
Permission Intel source schemas to a separate ObsidianDroid-owned evidence
database. It is not a migration runner and it does not authorize database
writes.

## Phase 1: complete locally, pending review

Phase 1 creates only design, validation, and evidence-preservation material:

- `database/core_migrations/0001_core_evidence_foundation.sql` is a reviewed,
  **un-applied** seven-table foundation.
- `scripts/core_migration/dry_run_evidence_migration.py` can build a
  deterministic plan from approved read-only source evidence; it contains no
  DDL or DML.
- `scripts/core_migration/generate_phase1_inventory.py` writes local source and
  artifact inventories. Its reports live under `inventory/`, are ignored by
  Git, and must be reviewed locally rather than treated as versioned source.
- `make check-phase1-closeout` performs an offline-only readiness check. It
  confirms that Core persistence is disabled, the design-only DDL has the
  expected evidence tables, all seven local inventory reports exist, and the
  July 18 fixture preview remains a nonpublication dry run with its expected
  row plan. It reports the exact DDL SHA-256 for the future migration receipt.
  It does not open a database connection.

An `OK` result means only that the Phase 1 review package is available for
human review. It does **not** authorize Phase 2, apply DDL, copy evidence,
change source schemas, or run a benchmark.

## Phase 2: separately approved work

The exact future prerequisites, transaction boundaries, validation queries,
and rollback approach are in [phase2_apply_plan.md](phase2_apply_plan.md).
Phase 2 remains blocked until a restore rehearsal, inventory review, dedicated
accounts/grants, and explicit approval are recorded.
