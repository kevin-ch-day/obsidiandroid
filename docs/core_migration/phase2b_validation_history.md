# Phase 2B disposable-validation history

Disposable schemas and receipts are retained; they are evidence, not failed
work to delete. The final frozen migration pair is `0001` SHA-256
`fd65d0106b50484da3ca802f8a2b98649f9bac06993989c5602f09d30c0badae`
and `0002` SHA-256
`076fefdc613e9f359f03c2156027009f0950df33b4e049cd501c523dcb4c9b21`.

| schema / receipt | outcome | status |
|---|---|---|
| `od_core_phase2b_validate_20260719T201500Z` | Import transaction rejected missing `core_quality_finding.source_record_hash`; zero Core runs rolled back. | superseded by corrected 0002 |
| `od_core_phase2b_validate_20260719T202000Z` | JSON constraint correctly rejected raw text conflict evidence; zero Core runs rolled back. | superseded by corrected mapper |
| `od_core_phase2b_validate_20260719T203000Z` | Earlier migration pair passed synthetic validation. | superseded because final 0002 contract changed |
| `od_core_phase2b_validate_20260719T211000Z` | Final pair passed migration, state, identity, import, and re-execution checks. | current review evidence |
| `20260720T055226Z-phase2b-empty-core` recovery package | Restore correctly fail-closed because the dump had a `.gz` name and gzip manifest field but plain SQL bytes. The retained package is marked `FAILED_PLAIN_DUMP`; no restore schema or Core evidence was created. | superseded by gzip-writer correction |
| `20260720T055352Z-phase2b-empty-core` recovery package → `od_core_restore_20260720t055352z_phase2b` | Checksum-bound empty-Core dump restored to a new disposable schema. Table set, row counts, table structures, routine count, and trigger count all matched. | current local recovery evidence |

The current local receipt SHA-256 values are
`ef82095125b6744d3f96929ddc0b6a655f8a1c9e096cdcb2d09bfad75a53987d`
and
`62c132c1e994801df8e288ca75b2b8343e1cc69ed09a9526a3c05c5956c3684b`.

The current recovery package manifest SHA-256 is
`adb52bec937f1f84145556bc6502aa0078ac27b6687711c431f5b3a769b81917`;
the compressed dump SHA-256 is
`3d1bc28fe6319edb7ffb1d04679dcc3357e78c5ad1ad430beb7606cc36a72f6b`.
Both packages and their credential-free receipts are retained outside Git under
the private Core-backup directory.
