# Phase 2C controlled fixture import: review gate

Phase 2C is **not authorized by this document**. It is the review checklist
for a future, separately approved import of one bounded fixture into the
already provisioned `obsidiandroid_core_prod` database. Core persistence and
normal pipeline routing remain disabled throughout Phase 2C.

## Preconditions that must be separately approved

1. Review a clean, committed source baseline and the exact fixture run ID.
   The committed `0001` and `0002` migration bytes must match the Core
   migration ledger exactly; the preserved Phase 2B package is the authority
   for the originally applied bytes.
2. Use the local Erebus reader to extract only the five approved base tables:
   `analysis_run`, `analysis_snapshot`, `analysis_snapshot_sample`,
   `analysis_artifact`, and `snapshot_label_conflict`. The approved command is
   `scripts/core_migration/create_phase2c_source_extract.py`; it is locked to
   the fixture run, uses one read-only consistent snapshot, and refuses the
   normal application database configuration.
3. Preserve minimal, content-addressed source extracts and a redacted manifest
   before any Core write. For every approved source surface, the manifest must
   record source table, approved column contract, extraction-query hash,
   observation timestamp, canonical serialization version, row count,
   ordered natural-key digest, content hash, and compressed-file hash. A
   zero-conflict result requires an explicit zero-row extract and manifest
   entry; an absent file is not evidence of zero. Hashes alone are not a claim
   of reconstructability.
4. Build the deterministic plan, review its source-run ID, row counts,
   source-record hash, and plan SHA-256. Reject a row-count or mapping
   discrepancy rather than repairing source data. Use
   `scripts/core_migration/build_phase2c_import_plan.py`, which first verifies
   every extract payload and binds per-table content and key-set hashes for the
   independent post-import reconciliation.
5. Create a human-reviewed `Phase2CImportAuthorization` v2 bound to that exact
   plan SHA-256, source-run ID, extract-manifest SHA-256, mapping-contract
   version, repository commit, both migration checksums, expected destination
   counts, server identity, writer account, and Core-preflight SHA-256. It must
   name an operator, issue and expiry timestamps, a diagnostic/non-publication
   fixture classification, and an explicit one-execution limit. Its consumption
   receipt is written to a private external ledger before the Core connection
   opens; any attempted use consumes the authorization. A feature flag,
   environment variable, or `allow_production` boolean is not sufficient
   authority.
6. Re-run the Core audit immediately before execution: seven expected tables,
   two migration rows with the exact applied checksums, zero Core evidence
   rows, persistence disabled, and the account/grant contract intact. Preserve
   a content-addressed empty-Core recovery artifact and bind the audit hash to
   the authorization.

## Controlled execution boundary

The importer may use only the dedicated Core writer account and only the
pre-reviewed plan. It must confirm the authorized server identity and writer
identity after connecting. It never reads source data itself, modifies an
Erebus row, copies artifact bytes, enables normal Core persistence, or routes
the pipeline to Core. It executes the Core inserts in one transaction and
records the plan-bound receipt ID in imported Core rows. A mismatch, duplicate
with a different source-record hash, or any unexpected Core state aborts the
import. Pre-commit failures roll back Core rows; after a commit, a failed audit
requires quarantine and separately approved remediation, never an automatic
writer-side delete.

## Required post-import review

Re-run the Core audit through the Core auditor account; reconcile destination
counts, key-set hashes, and canonical row hashes against the approved plan;
preserve the source extract, plan, authorization record, authorization
consumption receipt, execution receipt, and checksum manifest off-host. The
resulting import is a controlled fixture record only: it is not a paper
reproduction, live benchmark, or authorization for Phase 2D pipeline
integration.
