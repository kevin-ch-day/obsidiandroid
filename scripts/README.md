# Maintenance, diagnostics, and research scripts

Run these from the **repository root** so imports resolve (`obsidiandroid`, `database`, `config`, etc.):

```bash
cd /path/to/obsidiandroid
source .venv/bin/activate   # if using the project venv
python scripts/diagnose_alignment_gap.py --help
```

## Imports and coupling

- **Prefer** orchestration via `run_pipeline` — `from obsidiandroid.pipeline import run_pipeline` (canonical) or `from obsidiandroid.cli.pipeline_entry import run_pipeline` (CLI entry wrapper). Repo-root **`main.py`** remains a compatibility re-export surface for tests/operators.
- **Avoid** importing deep stage internals (`obsidiandroid.pipeline.stage_*`) from new scripts unless you are extending the pipeline; those modules assume full runtime context (`app_config`, diagnostics paths, profiles).
- **Database**: credentials come from `database/db_config.py` (environment variables `OBSIDIAN_DB_*`, optional repo-root `.env` via `python-dotenv`). Smoke-check connectivity before long jobs:

  ```bash
  make preflight-db
  # or: python -m database.split_db_health
  ```

- **Bootstrap**: repo entrypoints should use [`scripts/_bootstrap.py`](_bootstrap.py) instead of open-coding repeated `sys.path` and `runtime_bootstrap` setup. Top-level scripts still add the repo root once before importing `scripts._bootstrap`; nested `scripts/diagnostics/*` and `scripts/research/*` do the same with their deeper parent path.

## Layout

| Path | Role |
| --- | --- |
| `scripts/*.py` | Stable operator entrypoints plus compatibility wrappers for a few diagnostics that were moved under `scripts/diagnostics/`. |
| `scripts/dev/*` | Shell: venv bootstrap, startup menu, pytest helpers; Python: bytecode cleanup, import smoke, ML scan, data fuzzer (see [`dev/README.md`](dev/README.md)). |
| `scripts/diagnostics/*.py` | Canonical report, audit, and inspection CLIs. Prefer these paths for new docs and operator workflows. |
| `scripts/research/*.py` | Publication tables, evidence bundles, structural diagnostics. |

## Canonical diagnostics now under `scripts/diagnostics/`

These top-level names are still runnable for compatibility, but the canonical locations are:

| Compatibility entrypoint | Canonical path |
| --- | --- |
| `scripts/diagnose_alignment_gap.py` | `scripts/diagnostics/diagnose_alignment_gap.py` |
| `scripts/report_feature_lineage.py` | `scripts/diagnostics/report_feature_lineage.py` |
| `scripts/report_feature_matrix_gap.py` | `scripts/diagnostics/report_feature_matrix_gap.py` |
| `scripts/report_output_inventory.py` | `scripts/diagnostics/report_output_inventory.py` |
| `scripts/trace_feature_builder_drops.py` | `scripts/diagnostics/trace_feature_builder_drops.py` |
| `scripts/check_run_integrity.py` | `scripts/diagnostics/check_run_integrity.py` |

Top-level operator scripts that remain intentionally top-level for now include:
- `backfill_permission_trends_warehouse.py`
- `cleanup_output_artifacts.py`
- `fresh_pipeline_reset.py`
- `retrain_models_from_cached_alignment.py`
- `family_label_taxonomy_audit.py`
- `check_cohort_foundation.py`

Those are closer to run operations, warehouse maintenance, or cohort gating than pure diagnostics.

Release-hygiene note:
- `cleanup_output_artifacts.py` is the canonical on-disk cleanup tool for `output/` and repo-root runtime logs.
- It now repairs stale latest-run pointer files from a real manifest-backed run before syncing promoted pointers, and prunes stale run-bound `output/diagnostics/*.latest.*` mirrors that no longer match the current latest run.

For architecture context see [`docs/architecture.md`](../docs/architecture.md). Repository root layout during the src-package migration is summarized in [`docs/STRUCTURE_MIGRATION_PLAN.md`](../docs/STRUCTURE_MIGRATION_PLAN.md).
