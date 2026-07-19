# Retired ObsidianDroid research-ledger DDL draft

> **Do not apply these files.** They are an unimplemented historical v2.2.0
> design for the former `obsidiandroid_research` schema. They are retained only
> to preserve the planning record and are not part of the active database
> contract, test suite, migration path, or operator workflow.

The current, reviewed Phase 1 design targets the dedicated
`obsidiandroid_core_prod` database through the `OBSIDIANDROID_CORE_DB_*`
environment tuple. Its version-1 DDL is deliberately un-applied at
[`database/core_migrations/0001_core_evidence_foundation.sql`](../../core_migrations/0001_core_evidence_foundation.sql).
The controlled next step is documented in
[`docs/core_migration/phase2_apply_plan.md`](../../../docs/core_migration/phase2_apply_plan.md).

## Historical purpose

The ObsidianDroid research database stores **governed run outputs** — labels, membership, permission facts, metrics, predictions, quality flags, splits, and release manifests — not raw VT catalog or Permission Intel replication.

## Retained files (v2.2.0 historical draft)

| File | Purpose |
| --- | --- |
| `001_create_core_tables.sql` | Core tables, primary keys, foreign keys |
| `002_create_indexes.sql` | Secondary indexes for import and audit queries |
| `003_create_views.sql` | Read-only convenience views (draft) |

## Historical conventions

- **Clean table names** — no `od_` prefix; this is a dedicated schema.
- **Lazy `samples` registry** — rows are inserted only when a `sample_id` appears in curated run artifacts (label facts, membership, permission facts, prediction facts, release manifests). No bulk copy from Erebus.
- **Long-form permission truth** — `sample_permission_facts` is populated from **present-only** sparse `ml_sample_permission_feature_{run_id}.csv` (v2.2.0+); dense wide matrices are derived later for ML, not stored as DB source of truth.
- **Git provenance** — optional `source_git_commit`, `source_git_tag`, and `code_version` on `runs`; official release packaging lives in `release_manifests`.

## Retirement status

This draft was never applied. It must not be revived by changing environment
variables or running these SQL files. The active fail-closed core connection
does not fall back to primary Erebus credentials or this retired schema.
