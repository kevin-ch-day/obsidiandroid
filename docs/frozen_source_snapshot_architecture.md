# Immutable latest-state benchmark-source snapshots

## Architecture decision

The chosen architecture is a **filesystem evidence package**:

```text
mutable Erebus + Permission Intel
→ separately timed read-only extractions
→ immutable source snapshot package
→ validation, hashes, sealing
→ SealedSnapshotFrozenBenchmarkSourceProvider
→ frozen benchmark runner
```

The package is run-independent and may be reused by multiple development or benchmark runs without requerying mutable sources.

| Option | Benefits | Risks | Decision |
|---|---|---|---|
| Filesystem evidence package | Portable, content-addressed, independently verifiable, no benchmark DB access, straightforward retention | Requires controlled snapshot storage | **Chosen** |
| Append-only research snapshot schema | Central query surface and access control | Requires migration, database write authority, retention/immutability controls, and still cannot reconstruct historical VT reports | Deferred |

## Evidence meaning

VirusTotal evidence represents a sealed capture of the mutable latest-state vendor verdict row available at the declared extraction time. It does not reconstruct the original historical report or observation-time engine state.

Engine active/trusted values, taxonomy, and permission knowledge are likewise snapshot-time state. Primary and Permission Intel sources are extracted separately; cross-database atomicity is not guaranteed.

## Identity and lifecycle

Each snapshot carries a content-bound `snapshot_id`, schema version, creation/as-of timestamps, source commit, extractor version, redacted source identities, query hashes, row/content hashes, and temporal-limitation declaration.

```text
DRAFT → EXTRACTED → VALIDATED → SEALED
```

`SEALED` packages are immutable. Hash mismatch, missing file, path escape, symlink, `latest` naming, schema mismatch, invalid lifecycle history, or extraction-window violation is rejected. A correction requires a new snapshot identity.

Canonical extraction policy limits the elapsed window across the separately extracted databases to 300 seconds. A larger window fails canonical validation; a future explicit noncanonical snapshot may record the exception but cannot replace canonical evidence.

The operator records primary-start, primary-completion, Permission-Intel-start,
and Permission-Intel-completion UTC timestamps. Validation confirms that the
declared extraction-window duration matches those endpoints. This is an
extraction-time boundary only; it does not assert a shared cross-database
point-in-time view.

## Contents

The manifest references only relative files inside the snapshot root:

```text
source_snapshot_manifest.json
cohort_candidates_<snapshot_id>.csv.gz
android_metadata_<snapshot_id>.csv.gz
vt_wide_rows_<snapshot_id>.csv.gz
vt_long_normalized_<snapshot_id>.csv.gz
permission_observations_<snapshot_id>.csv.gz
permission_knowledge_<snapshot_id>.csv.gz
taxonomy_aliases_<snapshot_id>.csv.gz
engine_metadata_<snapshot_id>.csv.gz
duplicate_label_audit_<snapshot_id>.csv.gz
SHA256SUMS
```

The VT wide file preserves one indivisible captured source row per sample, including all selected engine-result columns and source `updated_at`. The long derivative is generated only from that sealed wide file. Every engine record for a sample references the same `source_wide_row_hash` and local `snapshot_row_id`; neither is represented as an original VT report identifier.

The manifest itself has an integrity hash, and every compressed extract has a
byte-level SHA-256 plus an ordered-content hash and row count. The provider
rejects a schema mismatch, unsealed package, incomplete lifecycle,
manifest/file modification, missing extract, symlink, root escape, global
`latest` filename, invalid time window, or a long AV table that cannot be
re-derived from the sealed wide rows. The provider loads validated frames once
and returns defensive copies, so the benchmark runner never opens a database.

## Authority governance

Duplicate authority candidates are not silently deduplicated. Equal family identity candidates are selected by declared priority with an audit row. Conflicting family ID/name candidates fail the snapshot build. The future production extractor must define source precedence before it can materialize a real package.

## Readiness boundary

This implementation contains only the filesystem package, its validation, a
snapshot-backed provider, and synthetic fixtures. It does not execute a real
extraction, materialize production rows, enable the direct database provider,
lock a real cohort, fit a real feature contract, or authorize a held-out
evaluation. A separately approved real extraction must supply the same
minimal source metadata for every extract and preserve the declared
latest-state temporal limitation.
