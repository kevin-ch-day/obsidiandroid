# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**[`docs/AGENTS.md`](docs/AGENTS.md) is the canonical, authoritative contributor/agent guide** (the repo-root `AGENTS.md` is only a pointer to it). Read it before non-trivial changes; this file summarizes the parts needed to get productive and should not diverge from it. If they conflict, `docs/AGENTS.md` wins.

## What this is

ObsidianDroid (v2.4.0, Python ≥3.11) is a research framework for Android malware family classification: it reads VirusTotal vendor verdicts and permission data from MySQL/MariaDB, normalizes AV labels, scores vendor engines, builds feature matrices, trains classifiers (RF, SVM, XGBoost, LR), and writes labels/diagnostics under `output/`. Runs are **profile-driven** (`profiles/*.yaml`, explicit selection required; `dev_fast` / `dev_smoke` for quick iteration).

## Commands

```bash
./setup.sh                      # or `make setup`: create .venv + install requirements.txt
source .venv/bin/activate && pip install -e .   # or `make install-editable`
./run.sh                        # or `make menu`: interactive startup menu (sets PYTHONPATH=src)

make test                       # fast pytest lane (excludes slow/integration/heavy/contract/pipeline_heavy)
make test-changed               # tests for modules touched vs origin/main (BASE=ref to override)
make test-integration           # integration marker lane
make test-pipeline-integration  # full partial run_pipeline lane (slowest)
make test-full                  # everything
make verify-canonical           # canonical-closure contract tests + baseline slot validation

make ci-fast                    # daily gate: doc-check + verify (import surface + fast tests) + ml-scan-strict
make ci                         # ci-fast + verify-canonical (pre-push gate)
make preflight-db               # DB connectivity check (needs OBSIDIAN_DB_* / .env)
```

Single test: `pytest -q tests/test_foo.py::test_bar` (pytest `addopts` excludes slow/integration/etc. markers by default; to run a marked test, override with e.g. `pytest -q -m "slow or not slow" tests/test_foo.py::test_bar`). `tests/conftest.py` prepends `src/` so no editable install is required for pytest.

CI (GitHub Actions) runs the fast lane on Python 3.11/3.12, plus integration lanes and `verify-canonical` on 3.12.

## Architecture (big picture)

- **Package:** all importable code is `src/obsidiandroid/`. Repo-root `analysis/`, `utils/`, `model/`, `ml_classification/`, `data_inspect`, `devtools` are **retired** — never import or recreate them. Repo-root `database/` holds **SQL assets only** (no Python there; don't move it as a drive-by). Python DB code is `src/obsidiandroid/database/`, exposed via a façade whose ordered name list lives in `obsidiandroid.database.facade_manifest`.
- **Entry points:** `main.py` is a thin shell (adds `./src` to `sys.path`) over `obsidiandroid.pipeline.runner.run_pipeline`. Tests may monkeypatch symbols on `main`; canonical code resolves those overrides via `obsidiandroid.cli.main_override_bridge`. Scripts should use `from obsidiandroid.pipeline import run_pipeline`. Console scripts (pyproject): `obsidiandroid` (startup menu), `obsidiandroid-assess`, `obsidiandroid-assess-doctor`, `obsidiandroid-pi-v2`.
- **Pipeline flow** (`pipeline/runner.py` orchestrates `stage_*` modules): preflight → `stage_samples` (cohort load + gates) → `stage_av_vendor` (AV analysis, vendor parsing via `obsidiandroid.vendors`, alignment) → `stage_feature_enrichment` → `stage_modeling` (engine weights, feature matrix, training via `obsidiandroid.modeling`, label resolution) → optional `stage_ablation`, `stage_permission_trends_report` → `stage_manifest` (run manifest, evidence exports) → `stage_results_warehouse` (only when configured). `PipelineRunBounds` (`pipeline.run_bounds`) holds run-scoped paths; prefer `get_pipeline_run_bounds()` over re-deriving paths from `config/app_config.py`.
- **Two databases:** primary Erebus schema (samples, VT verdicts, taxonomy) and Permission Intel schema (`android_permission_*`), configured via `OBSIDIAN_DB_*` env vars in `obsidiandroid.database.db_config` (typed: `database.settings.load_connection_settings()`). MySQL 8+ window functions are assumed. Ownership: Erebus owns sample/VT/taxonomy facts, Permission Intel owns permission facts; ObsidianDroid only consumes them and owns its downstream run/result/assessment persistence. Normal runs are read-only upstream — check source and Core DB identities before anything write-oriented.
- **Where things live:** `common` (hashing, path safety, `output_paths`, export helpers, `time_display`), `observability.logging` (structured/tee logs) and `observability.pipeline_observability` (JSONL timeline, stage summary, run health), `diagnostics` (run diagnostics, inventories, research validity, hostile audit), `reporting.export_manager` (Excel/vendor/confusion-matrix exports), `governance` (run manifests), `cli` (menu, profiles, `cli.ui.display` for console output).
- **Outputs:** `output/` and `logs/` are runtime-generated and gitignored; `artifacts/baselines/` is the intentional home for preserved evidence/regression baselines.

## Rules that are enforced or easy to break

- **Import-surface ratchets:** `scripts/dev/check_import_surface.py` (policy in `scripts/dev/import_surface_policy.py`) fails if `src/`, `scripts/`, or tests import retired roots (`analysis`, `ml_classification`, root `database`, root `main` from canonical code), if `src/` modules have stale `# Filename:` headers naming those roots, or if `.py` files have a UTF-8 BOM. Run it after touching `src/obsidiandroid/` or import layout.
- **`make doc-check`** blocks reintroduced phantom paths in README/key docs — keep doc references to real paths.
- **ML static scan** (`make ml-scan-strict`) flags suspicious `.predict()` / `.predict_proba()` call sites.
- **Offline DB guard:** `scripts/dev/pytest_database_guard.py` blocks real MySQL connections and sockets in tests. The `integration` marker does not authorize live access; live tests need both the `live_database` marker and `--allow-live-database` (never in offline CI).
- **Slow tests:** whole modules listed in `_SLOW_TEST_MODULES` in `tests/conftest.py` are auto-marked `slow`. Prefer narrow unit tests outside those modules.
- **Paper cohort identity:** the active locked benchmark is `20260504T044304Z__8c64e6` (1226 samples / 39 families / 6 types; `artifacts/baselines/20260504T044304Z__8c64e6/cohort_lock_manifest.json`). `20260526T021235Z__8b6966` is archival drift evidence only. Don't conflate historical locks, generated paper exports, current diagnostics, and operational assessments; verify profile, source snapshot, run manifest, and `paper_mode` before making manuscript/readiness claims. Use `scripts/diagnostics/export_cohort_census.py` and `audit_locked_cohort_gap.py` rather than ad-hoc SQL for cohort questions.
- **Timestamps:** human-facing times go through `obsidiandroid.common.time_display.format_timestamp` (America/Chicago + UTC); keep machine-readable UTC values intact.
- **Style:** PEP 8, type hints where they clarify contracts, Google-style docstrings for public APIs; forward-slash paths or `pathlib` (never backslash path literals).
- Keep `pyproject.toml` `packages.find.include` aligned with real top-level packages. Update `README.md` when user-visible commands/behavior change. The working tree often has unrelated in-progress edits — check `git status` and preserve them.
