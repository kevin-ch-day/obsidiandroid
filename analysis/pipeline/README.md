# Pipeline package (`analysis/pipeline`)

End-to-end staged workflow for cohort loading, AV/vendor processing, features, training, ablation, reporting, and manifest finalization.

**Migration note:** Runner-linked pipeline code is **canonical** under **`obsidiandroid.pipeline`** (`src/obsidiandroid/pipeline/`), and governance helpers are canonical under **`obsidiandroid.governance`**. The remaining `analysis/pipeline` tree is the final protected compatibility shell: `runner.py`, `main_facade.py`, and the package root register legacy nested aliases in `sys.modules` so `import analysis.pipeline.*` continues to resolve to the same `ModuleType` objects as the canonical `obsidiandroid.*` modules. Prefer **`from obsidiandroid.pipeline import …`** and **`from obsidiandroid.governance import …`** in new code; see [`docs/STRUCTURE_MIGRATION_PLAN.md`](../../docs/STRUCTURE_MIGRATION_PLAN.md).

| Module | Role |
| --- | --- |
| **`runner.py`** | **`run_pipeline`** — stage ordering, evidence/paper paths, timing, manifest hooks. Invoked from **`main.py`** and **`obsidiandroid.cli.pipeline_entry`**. |
| **`main_facade.py`** | Resolves monkeypatched symbols on **`main`** so tests can stub stages while orchestration lives in **`runner`**. |
| **`run_bounds.py`** | **`PipelineRunBounds`**: frozen snapshot of `run_id`, `diagnostics_dir`, run/output roots. Set from **`runner`** after profile load and evidence/paper path remapping; cleared in **`finally`**. |
| **`stage_*.py`** | Stage implementations (`stage_samples`, `stage_av_vendor`, …) — **canonical:** `obsidiandroid.pipeline.stage_*`; **this tree:** identity shims. |
| **Nested `analysis.pipeline.*` imports** | Compatibility aliases registered by `analysis.pipeline.__init__` for `artifacts`, `manifest`, `permission_trends`, and `governance` package/submodule paths. |
| **`runtime_policy.py`** | Profile-driven feature flags and config mutations for a run. |

## Cross-run `app_config` hygiene

Some stages stash filesystem paths on `app_config` (overlay CSVs, split audit metadata,
permission/feature survival exports). Under strict run-scoped artifact enforcement, a
**stale path from another test or an earlier CLI invocation** can make the next
`run_pipeline` fail with `[INTEGRITY] non-run-scoped artifacts`.

`runtime_policy.CROSS_RUN_ARTIFACT_POINTERS` lists those keys; `clear_cross_run_artifact_path_pointers()`
resets them before each `run_pipeline` snapshot and inside `reset_runtime_markers()`.
`run_pipeline` also calls `reset_runtime_training_caches()` before the config snapshot so
`RUNTIME_TRAINING_STATE` (split reuse caches keyed by `RUNTIME_RUN_ID`) does not accumulate
across tests; `RUNTIME_TRAINING_STATE` is part of `build_mutable_config_keys()` so `finally`
restores the pre-run value after each invocation.

When adding new `RUNTIME_*` paths that the runner may register as artifacts, extend that
map and `build_mutable_config_keys()` together (see `tests/test_runtime_policy_cross_run_cleanup.py`).

## CLI / test bridge (`main_facade`)

Integration tests that stub pipeline stages via `import main` should patch attributes
resolved through `main_facade.from_main_or` (see the module docstring there). Other stages
are usually patched on `analysis.pipeline.runner`.

Extension guide: [`docs/pipeline_staging_guide.md`](../../docs/pipeline_staging_guide.md).

## Cohort audit (SQL scope vs prepared rows)

- **Vocabulary:** [`analysis/diagnostics/cohort_vocabulary.py`](../diagnostics/cohort_vocabulary.py) — canonical manifest keys and legacy mirrors.
- **Samples-only run:** `run_pipeline(..., stop_after="samples")` writes `diagnostics/cohort_foundation.*`, snapshot/time-contract, and `preflight_report.json` (cohort audit path).
- **DB reconciliation (needs MySQL):** `python scripts/check_cohort_foundation.py --profile <id>` — SELECT-only counts vs profile gates.

## Ablation bookkeeping and operator interrupts

- **`ablation_run_outcome_<run_id>.json`** records `ablation_grid_status` (`complete` / `failed` / `interrupted`) whenever the ablation training grid is entered. If the process is **SIGKILL’d** or **OOM-killed**, neither this file nor **`run_manifest.json`** is guaranteed (no Python `finally` runs).
- **`KeyboardInterrupt`** logs an **`INTERRUPTED`** `STAGE_END`, runs manifest finalization best-effort (exit code **130**), and may leave **`ablation_summary_partial_<run_id>.csv`** plus **`ablation_summary_partial.latest.csv`** when partial rows completed.
- **`RuntimeError` / `Exception` during ablation** emits **`FAIL`** for the ablation stage and still finalizes the run manifest on the normal exception path (`docs/AGENTS.md` CI parity).
- **`stop_after="ablation"`** is the supported cut point when you only need methodology exports through that stage; **`profiles/dev_ablation_fast.yaml`** is an RF-only / reduced label-target profile for faster grids.
- **`vendor_merge_n` vs governed cohort:** documented on `feature_build_coverage_*.json` (`vendor_merge_n_semantics`) and `feature_modality_coverage_summary_*.json` (`vendor_merge_n_note`).
