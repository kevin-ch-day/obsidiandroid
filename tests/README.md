# Tests

- **`tests/` vs QA helpers:** Pytest collects only this tree. Canonical QA helpers (synthetic fuzzer, ML predict scan) live under **`scripts.dev`** (`scripts/dev/` on disk). Example: **`from scripts.dev import data_fuzzer`** or **`python scripts/dev/data_fuzzer.py`**.
- **Default run:** `pytest` / `make test` — respects **`pyproject.toml`** `[tool.pytest.ini_options]` (`-m "not slow"`). See `tests/conftest.py` for the `_SLOW_TEST_MODULES` list and temp output routing. Pytest basetemp is `.pytest_tmp/` at the repo root (gitignored).
- **Full run:** `make test-full` — includes slow integration modules (manifest, menus, heavy stages).
- **Policy:** add focused unit tests next to the code you change; register heavy modules in `_SLOW_TEST_MODULES` so the fast loop stays usable.

Contributor/agent notes: **[`docs/AGENTS.md`](../docs/AGENTS.md)** (repo-root `AGENTS.md` points there). See also **`docs/developer_guide.md`**.

## Test-suite consolidation notes

A quick AST census of `tests/test_*.py` currently shows **155 test modules**, **1,310 test functions**, and roughly **41.6k lines**. Keep pruning focused on collection overhead and duplicate domain coverage rather than deleting assertions.

Applied cleanup:

- Merged GridSearch/CV-fold coverage from `test_grid_search_parallel_layout.py` into `test_parallel_layout.py`; both files exercised `obsidiandroid.modeling.parallel_layout` and split the same job-count contract.
- Merged runtime stream logging coverage from `test_runtime_logging.py` into `test_observability_api.py`; both files covered observability entry points and can share one import/fixture surface.

Good next consolidation candidates:

- Ablation micro-contracts: `test_ablation_registry.py`, `test_ablation_split_feature_columns.py`, and the narrower portions of `test_stage_ablation.py`.
- Log/report diagnostics: `test_report_log_surface.py` and `test_report_run_log_issues.py`.
- Small cohort helper modules: `test_cohort_loader_contract.py`, `test_cohort_sample_id_audit.py`, and narrowly related sections of `test_sample_metadata_fetchers.py`.
- Tiny policy smoke files with one or two tests, such as `test_paper_family_display_policy.py`, can usually move into the nearest governance/paper contract module.

When merging, prefer moving tests unchanged first, then deduplicate helpers in a separate commit so failures remain easy to bisect.
