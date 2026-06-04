## SQL Layout

`database/sql/` is the active SQL surface for this repo.

For the production release, this directory is intentionally limited to:
- live authority schema foundations and loaders
- active authority views and smoke checks
- queue-maintenance SQL still referenced by operator docs

Legacy audit/worklist SQL that existed only as already-applied or test-only payloads
should be deleted instead of kept here.

Keep these in the top level:
- shared schema foundations
- active views
- audits and worklists that code, tests, or docs reference directly
- reusable SQL that operators are expected to run by name

Delete these instead of retaining them after use:
- one-off applied tranche files
- generated ingest batches that have already been loaded
- bounded repair scripts kept only for provenance
- ad hoc diagnostics that are no longer referenced outside `database/sql/`

Rule of thumb:
- if a SQL file is part of the active contract surface, keep it here
- if it is no longer referenced and only records an already-applied one-off change, delete it
