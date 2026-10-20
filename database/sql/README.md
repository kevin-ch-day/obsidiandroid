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

Applied one-off repair scripts that you still want locally should live under
`database/local_applied/` (gitignored), not in this top-level contract surface.

Delete these instead of retaining them after use:
- one-off applied tranche files
- generated ingest batches that have already been loaded
- bounded repair scripts kept only for provenance
- ad hoc diagnostics that are no longer referenced outside `database/sql/`

Rule of thumb:
- if a SQL file is part of the active contract surface, keep it here
- if it is no longer referenced and only records an already-applied one-off change, delete it

## Read-only audit execution

Do not execute this directory as a batch: foundation, seed, backfill, view and
queue-pruning files contain production mutations. Read-only entrypoints are
label_authority_audit.sql, label_authority_schema_smoke.sql,
view_android_sample_family_type_authority_smoke.sql, and
malware_artifact_ingest_queue_buffer_audit.sql. Run reviewed queries with the
normal reader, a server-enforced read-only session, an explicit statement timeout
and result bounds. A failed EXPLAIN on a definer view may reflect missing
underlying-object privileges; do not broaden grants to obtain a plan.

The label-authority checks explicitly use the catalog's utf8mb4_general_ci
comparison semantics to bridge the older alias/authority foundation's
utf8mb4_unicode_ci fields and avoid server-default collation drift. This changes
query comparisons only, not stored data or schema collations. The queue audit
expects the current hash-registry SHA-256 primary key and case-insensitive hash
columns. It uses indexed equality and EXISTS, counting each queue row once.
Counts identify review candidates and do not authorize deletion.

Check parsed-family coverage alongside the vendor disagreement query: zero
disagreement rows with missing parsed tokens cannot establish agreement.
