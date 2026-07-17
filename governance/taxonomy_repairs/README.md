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

`before_state_capture_mode` must accurately distinguish contemporaneous state
from reconstructed state. Do not place credentials, raw sample IDs, package
names, APK hashes, or full source extracts in a receipt.

See [TEMPLATE.md](TEMPLATE.md) before proposing any future repair.
