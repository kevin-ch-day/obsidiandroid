# ObsidianDroid research database DDL (draft)

**Schema / database name:** `obsidiandroid_research`  
**Environment variable:** `OBSIDIANDROID_RESEARCH_DB_NAME` (defaults to `obsidiandroid_research`)

This directory holds **DDL drafts only** for the curated ObsidianDroid research ledger. It is separate from Erebus authority SQL in the parent [`database/sql/`](../README.md) tree.

## Purpose

The ObsidianDroid research database stores **governed run outputs** — labels, membership, permission facts, metrics, predictions, quality flags, splits, and release manifests — not raw VT catalog or Permission Intel replication.

## Files (V3.1.0)

| File | Purpose |
| --- | --- |
| `001_create_core_tables.sql` | Core tables, primary keys, foreign keys |
| `002_create_indexes.sql` | Secondary indexes for import and audit queries |
| `003_create_views.sql` | Read-only convenience views (draft) |

## Conventions

- **Clean table names** — no `od_` prefix; this is a dedicated schema.
- **Lazy `samples` registry** — rows are inserted only when a `sample_id` appears in curated run artifacts (label facts, membership, permission facts, prediction facts, release manifests). No bulk copy from Erebus.
- **Long-form permission truth** — `sample_permission_facts` is populated from sparse `ml_sample_permission_feature_{run_id}.csv`; dense wide matrices are derived later for ML, not stored as DB source of truth.
- **Git provenance** — optional `source_git_commit`, `source_git_tag`, and `code_version` on `runs`; official release packaging lives in `release_manifests`.

## V3.1.0 status

DDL draft + dry-run importer only. **No runtime pipeline writes** and **no live importer `--apply`** in this milestone.

See [`docs/OBSIDIANDROID_DB_PLAN.md`](../../../docs/OBSIDIANDROID_DB_PLAN.md) for the full design.
