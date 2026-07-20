# Phase 2C controlled fixture import: review gate

Phase 2C is **not authorized by this document**. It is the review checklist
for a future, separately approved import of one bounded fixture into the
already provisioned `obsidiandroid_core_prod` database. Core persistence and
normal pipeline routing remain disabled throughout Phase 2C.

## Preconditions that must be separately approved

1. Review a clean, committed source baseline and the exact fixture run ID.
2. Use the local Erebus reader to extract only the five approved base tables:
   `analysis_run`, `analysis_snapshot`, `analysis_snapshot_sample`,
   `analysis_artifact`, and `snapshot_label_conflict`.
3. Preserve minimal, content-addressed source extracts and a redacted manifest
   before any Core write. Hashes alone are not a claim of reconstructability.
4. Build the deterministic plan, review its source-run ID, row counts,
   source-record hash, and plan SHA-256. Reject a row-count or mapping
   discrepancy rather than repairing source data.
5. Create a human-reviewed `Phase2CImportAuthorization` bound to that exact
   plan SHA-256 and source-run ID. A feature flag, environment variable, or
   `allow_production` boolean is not sufficient authority.
6. Re-run the Core audit immediately before execution: seven expected tables,
   two migration rows, zero Core evidence rows, persistence disabled, and the
   account/grant contract intact.

## Controlled execution boundary

The importer may use only the dedicated Core writer account and only the
pre-reviewed plan. It never reads source data itself, modifies an Erebus row,
copies artifact bytes, enables normal Core persistence, or routes the pipeline
to Core. It executes the Core inserts atomically and records the plan-bound
receipt ID in imported Core rows. A mismatch, duplicate with a different
source-record hash, or any unexpected Core state aborts the import.

## Required post-import review

Re-run the Core audit; reconcile each destination count against the approved
plan; preserve the source extract, plan, authorization record, execution
receipt, and checksum manifest off-host. The resulting import is a controlled
fixture record only: it is not a paper reproduction, live benchmark, or
authorization for Phase 2D pipeline integration.
