# Maintenance and research scripts

Run these from the **repository root** so imports resolve (`obsidiandroid`, `database`, `config`, etc.):

```bash
cd /path/to/obsidiandroid
source .venv/bin/activate   # if using the project venv
python scripts/diagnose_alignment_gap.py --help
```

## Imports and coupling

- **Prefer** orchestration via `run_pipeline` — `from obsidiandroid.pipeline import run_pipeline` (canonical) or `from obsidiandroid.cli.pipeline_entry import run_pipeline` (CLI entry wrapper). For legacy/compat: `from main import run_pipeline` and `from utils.pipeline_entry import run_pipeline` remain supported shims.
- **Avoid** importing deep stage internals (`obsidiandroid.pipeline.stage_*`) from new scripts unless you are extending the pipeline; those modules assume full runtime context (`app_config`, diagnostics paths, profiles).
- **Database**: credentials come from `database/db_config.py` (environment variables `OBSIDIAN_DB_*`, optional repo-root `.env` via `python-dotenv`). Smoke-check connectivity before long jobs:

  ```bash
  make preflight-db
  # or: python -m database.split_db_health
  ```

## Layout

| Path | Role |
| --- | --- |
| `scripts/*.py` | Operator tools (cleanup, lineage, alignment diagnostics). |
| `scripts/dev/*` | Shell: venv bootstrap, startup menu, pytest helpers; Python: bytecode cleanup, import smoke, ML scan, data fuzzer (see [`dev/README.md`](dev/README.md)). |
| `scripts/diagnostics/*.py` | Data/inspection helpers (canonical; repo-root `data_inspect/` removed — use `scripts.diagnostics`). |
| `scripts/research/*.py` | Publication tables, evidence bundles, structural diagnostics. |

For architecture context see [`docs/architecture.md`](../docs/architecture.md). Repository root layout during the src-package migration is summarized in [`docs/STRUCTURE_MIGRATION_PLAN.md`](../docs/STRUCTURE_MIGRATION_PLAN.md).
