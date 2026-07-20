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
write to one reviewed source extract and deterministic plan. Phase 2D remains
separately authorized pipeline integration.

## Earlier Phase 2 planning material

[phase2_apply_plan.md](phase2_apply_plan.md) is retained only as historical
context. Use the current Phase 2B contract and provisioning runbook instead.
