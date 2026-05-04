# Developer tooling (`scripts/dev/`)

Scripts here support **package layout and import hygiene**, not pipeline execution.

| Script | Purpose |
|--------|---------|
| [`check_import_surface.py`](check_import_surface.py) | Smoke-test `obsidiandroid` imports (`cli`, `pipeline`, `common`) and shim parity; exits nonzero on failure. |

From the repository root (after `pip install -e .` or `export PYTHONPATH="$PWD/src:$PYTHONPATH"`):

```bash
python scripts/dev/check_import_surface.py
# or:
make dev-import-check
```

See also [`STRUCTURE_MIGRATION_PLAN.md`](../../STRUCTURE_MIGRATION_PLAN.md) and [`AGENTS.md`](../../AGENTS.md).
