# Phase 1 closeout contract

Phase 1 is a read-only preservation and design phase. It does not apply Core
DDL, change source schemas, migrate records, alter database routing, or create
a Core persistence writer.

## Local review package

`scripts/core_migration/generate_phase1_inventory.py` creates an ignored local
package at `docs/core_migration/inventory/`. Each report carries its schema
version, UTC generation time, generator commit, and source-observation time.
`phase1_report_package_manifest.json` records report row counts and SHA-256
values; its `.sha256` sidecar validates the manifest itself.

The required reports are:

1. `derived_object_inventory.csv`
2. `warehouse_writer_inventory.csv`
3. `run_evidence_inventory.csv`
4. `artifact_recoverability_inventory.csv`
5. `migration_gap_inventory.csv`
6. `core_migration_disposition_matrix.md`
7. `preservation_risk_summary.md`

The generated package is evidence for human review, not a substitute for a
versioned migration specification. Raw inventories, production paths, dumps,
and artifacts remain outside Git unless separately approved.

## Evidence rules

- A `.latest` path is a mutable alias, never immutable run evidence.
- An artifact ledger row does not establish that its file exists.
- Missing historical artifacts remain metadata-only records.
- A historical run receives a positive feature, split, metric, or prediction
  status only when that exact run-local artifact is present and validated.
- A missing legacy migration remains `intent_unknown` unless an explicit script
  or preserved source proves otherwise.

## Phase 1 test boundary

`core_persistence_lifecycle` is a synthetic-only, dependency-injected failure
boundary. It proves that artifacts are finalized before a future Core write is
attempted and that a failed attempt cannot be reported as an import or applied
migration. It is not a production Core writer and must not be used to bypass
the Phase 2 DDL, authorization, or routing review.

## Closeout gate

`scripts/core_migration/check_phase1_closeout.py` is offline-only. It checks
the local report contracts, coverage, package checksums, diagnostic fixture
classification, disabled Core persistence, reviewed DDL, and presence of the
synthetic lifecycle test. A pass means the Phase 1 package is internally
consistent. It does not authorize Phase 2A, 2B, 2C, or 2D.
