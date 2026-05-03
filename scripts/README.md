# Maintenance and research scripts

Run these from the **repository root** so imports resolve (`analysis`, `database`, `config`, etc.):

```bash
cd /path/to/obsidiandroid
source .venv/bin/activate   # if using the project venv
python scripts/diagnose_alignment_gap.py --help
```

## Imports and coupling

- **Prefer** orchestration via `run_pipeline` — either `from main import run_pipeline` (CLI parity) or `from utils.pipeline_entry import run_pipeline` (stable shortcut to `analysis.pipeline.runner`).
- **Avoid** importing deep stage internals (`analysis.pipeline.stage_*`) from new scripts unless you are extending the pipeline; those modules assume full runtime context (`app_config`, diagnostics paths, profiles).
- **Database**: credentials come from `database/db_config.py` (environment variables `OBSIDIAN_DB_*`, optional repo-root `.env` via `python-dotenv`). Smoke-check connectivity before long jobs:

  ```bash
  make preflight-db
  # or: python -m database.split_db_health
  ```

## Layout

| Path | Role |
| --- | --- |
| `scripts/*.py` | Operator tools (cleanup, lineage, alignment diagnostics). |
| `scripts/research/*.py` | Publication tables, evidence bundles, structural diagnostics. |

For architecture context see [`docs/architecture.md`](../docs/architecture.md).
