# Taxonomy repair receipts

Each dated directory is a version-controlled receipt for one narrowly scoped,
approved live-database taxonomy repair. A receipt is evidence of what changed;
it is not a database migration framework and its SQL is never run by CI.

Required package files:

```text
receipt.json
evidence.md
before.sql
apply.sql
validate.sql
rollback.sql
SHA256SUMS
```

Run the offline validator from the repository root:

```bash
python -m obsidiandroid.governance.taxonomy_repair_receipts governance/taxonomy_repairs
```

The validator discovers every dated repair directory, including incomplete
ones. It rejects a missing required file, a checksum mismatch, a duplicate
`repair_id`, or prohibited sensitive fields. Do not leave a partial dated
directory in this tree while preparing a cohort lock.

## Cohort-lock binding

Newly exported cohort-lock manifests record a deterministic
`taxonomy_repair_receipt_set_hash` when this receipt tree validates. The hash
identifies the reviewed receipt artifacts available when the lock was written;
it does **not** replace the frozen row-level label snapshot or prove the
database contents by itself. An invalid receipt tree blocks creation of that
hash rather than being recorded as an empty, ambiguous value.

For a canonical held-out benchmark, the separate frozen-benchmark lifecycle
also requires a clean Git tree and the exact source commit. A receipt should
therefore be finalized and committed before it is treated as part of a
canonical experiment's governance evidence.

`before_state_capture_mode` must accurately distinguish contemporaneous state
from reconstructed state. Do not place credentials, raw sample IDs, package
names, APK hashes, or full source extracts in a receipt.

See [TEMPLATE.md](TEMPLATE.md) before proposing any future repair.
