# Maintenance, diagnostics, and research scripts

Run these from the **repository root** so canonical imports resolve (`obsidiandroid`, `config`, etc.):

```bash
cd /path/to/obsidiandroid
source .venv/bin/activate   # if using the project venv
python scripts/diagnostics/diagnose_alignment_gap.py --help
```

## Imports and coupling

- **Prefer** orchestration via `run_pipeline` — `from obsidiandroid.pipeline import run_pipeline` (canonical) or `from obsidiandroid.cli.pipeline_entry import run_pipeline` (CLI entry wrapper). Repo-root **`main.py`** remains a compatibility re-export surface for tests/operators.
- **Avoid** importing deep stage internals (`obsidiandroid.pipeline.stage_*`) from new scripts unless you are extending the pipeline; those modules assume full runtime context (`app_config`, diagnostics paths, profiles).
- **Database**: credentials come from `obsidiandroid.database.db_config` (environment variables `OBSIDIAN_DB_*`, optional repo-root `.env` via `python-dotenv`). Smoke-check connectivity before long jobs:

  ```bash
  make preflight-db
  # canonical: python -m obsidiandroid.database.split_db_health
  ```

- **Bootstrap**: repo entrypoints use [`scripts/_bootstrap.py`](_bootstrap.py) rather than open-coding `sys.path` setup. Top-level scripts add the repo root once before importing `scripts._bootstrap`; nested `scripts/diagnostics/*` and `scripts/research/*` do the same with their deeper parent path.
- **Runtime boundary**: reusable application logic belongs under `src/obsidiandroid/`; production modules must not import from `scripts/`. Scripts are CLI, maintenance, or developer surfaces. Vendor-output validation and classifier-summary rendering live under `obsidiandroid.diagnostics`; the historical helper scripts were removed.

## Layout

| Path | Role |
| --- | --- |
| `scripts/*.py` | Stable cohort-gate, taxonomy-audit, retraining, and dry-run import entrypoints. |
| `scripts/dev/*` | Shell: venv bootstrap, startup menu, pytest helpers; Python: bytecode cleanup, import smoke, ML scan, data fuzzer (see [`dev/README.md`](dev/README.md)). |
| `scripts/diagnostics/*.py` | Canonical report, audit, and inspection CLIs. Prefer these paths for new docs and operator workflows. |
| `scripts/maintenance/*.py` | Explicit database/state-changing maintenance commands (see [`maintenance/README.md`](maintenance/README.md)). |
| `scripts/research/*.py` | Publication tables, evidence bundles, structural diagnostics (see [`research/README.md`](research/README.md)). |

## Diagnostics entrypoints

Diagnostics are supported only under `scripts/diagnostics/`. The former
top-level diagnostic wrappers were removed; update any local automation to use
the canonical paths shown in that directory.

Top-level operator scripts that remain intentionally top-level include:
- `retrain_models_from_cached_alignment.py`
- `family_label_taxonomy_audit.py`
- `check_cohort_foundation.py`

Those are closer to run operations, taxonomy audit, or cohort gating than pure diagnostics.

Release-hygiene note:
- `maintenance/cleanup_output_artifacts.py` is the canonical on-disk cleanup tool for `output/` and repo-root runtime logs.
- Its default mode is a dry run; use `--apply` only after reviewing the proposed removals.
- It now repairs stale latest-run pointer files from a real manifest-backed run before syncing promoted pointers, and prunes stale run-bound `output/diagnostics/*.latest.*` mirrors that no longer match the current latest run.

For architecture context see [`docs/architecture.md`](../docs/architecture.md). Repository root layout during the src-package migration is summarized in [`docs/STRUCTURE_MIGRATION_PLAN.md`](../docs/STRUCTURE_MIGRATION_PLAN.md).
