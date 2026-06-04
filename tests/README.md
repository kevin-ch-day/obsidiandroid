# Tests

- **`tests/` vs QA helpers:** Pytest collects only this tree. Canonical QA helpers (synthetic fuzzer, ML predict scan) live under **`scripts.dev`** (`scripts/dev/` on disk). Example: **`from scripts.dev import data_fuzzer`** or **`python scripts/dev/data_fuzzer.py`**.
- **Default run:** `pytest` / `make test` — respects **`pyproject.toml`** `[tool.pytest.ini_options]` (`-m "not (slow or integration or heavy or contract)"`). See `tests/conftest.py` for the `_SLOW_TEST_MODULES` list and temp output routing. Pytest basetemp is `.pytest_tmp/` at the repo root (gitignored).
- **Full run:** `make test-full` — overrides the default marker filter and runs the entire suite.
- **Marker policy:** keep the fast loop focused on cheap logic and narrow contracts. Use `slow` for whole expensive modules, `contract` for broad deterministic governance/report/manifest checks, `integration` for stage/menu/report contracts with notable orchestration cost, and `heavy` for plotting/export or similar especially expensive checks.

Contributor/agent notes: **[`docs/AGENTS.md`](../docs/AGENTS.md)** (repo-root `AGENTS.md` points there). See also **`docs/developer_guide.md`**.

## Test-suite consolidation notes

A quick AST census of `tests/test_*.py` currently shows **143 test modules**, **1,310 test functions**, and roughly **41.6k lines**. Keep pruning focused on collection overhead and duplicate domain coverage rather than deleting assertions.

Applied cleanup:

- Merged GridSearch/CV-fold coverage from `test_grid_search_parallel_layout.py` into `test_parallel_layout.py`; both files exercised `obsidiandroid.modeling.parallel_layout` and split the same job-count contract.
- Merged runtime stream logging coverage from `test_runtime_logging.py` into `test_observability_api.py`; both files covered observability entry points and can share one import/fixture surface.
- Merged singleton permission-signal quality coverage into `test_permission_signal_seed.py`.
- Merged paper family-display policy coverage into `test_paper_cohort_contract.py`.
- Merged authority-coverage menu coverage into `test_family_type_authority_coverage.py`.
- Merged stage-samples package-integrity coverage into `test_stage_samples_contract_filters.py`.
- Merged ablation registry/split-cache micro-contracts into `test_stage_ablation.py`.
- Merged run-log issue coverage into `test_report_log_surface.py`.
- Merged cohort duplicate-grain and duplicate-sample-id audit coverage into `test_sample_metadata_fetchers.py`.
- Merged Android missing-resolution triage script coverage into `test_report_vt_false_positive_review_triage.py`.
- Merged profile-tuning snapshot coverage into `test_startup_menu.py`.
- Merged Zimperium IOC repo coverage into `test_zimperium_ingest_tranche.py`.
- Reclassified the worst profiled hotspots out of the default loop:
  - expensive startup-menu review / diagnostics contract tests -> `integration`
  - plotting-heavy permission-trends line-plot exports -> `heavy`
  - costly `stage_samples` wiring / failure-path tests in `test_sample_metadata_query_layer.py` -> `integration`
  - full `startup_menu_review` operator review-flow suite -> `integration`
  - run evidence/science index rendering tests in `test_output_inventory.py` -> `integration`
  - remaining `stage_samples_*` orchestration tests in `test_sample_metadata_query_layer.py` -> `integration`, leaving only pure loader/query contract checks in the default lane
  - diagnostics/menu surfaces in `test_startup_menu_diagnostics.py` and `test_vendor_diagnostics_menu.py` -> `integration`
  - run-science/report provenance and artifact-state resolution surfaces in `test_diagnostic_provenance.py` and `test_run_artifact_state.py` -> `integration`
  - full operator dashboard issue/report surfacing suite in `test_operator_dashboard.py` -> `integration`
  - broad deterministic reporting/governance suites such as diagnostics banners, run health, cohort readiness, taxonomy target-surface summaries, and research-health summaries -> `contract`
  - random-forest performance / diagnostics checks in `test_random_forest_performance.py` -> `contract`
  - the large confusion-matrix export path in `test_confusion_matrix_layout.py` was rewritten as a deterministic artifact-contract test so it stays cheap in the default lane
  - expensive `test_profile_preflight.py` was kept in the default lane, but its re-prompt flow now stubs readiness/inventory lookups so the test stays cheap without losing coverage

Good next consolidation candidates:

- Remaining small report/export candidates: nearby diagnostics-script coverage around export/report helpers that already share fixtures or fake database surfaces.
- Small startup/report smoke files such as `test_runner_support.py` and adjacent narrow menu/export modules are still worth reviewing for grouping opportunities.
- Tiny policy smoke files with one or two tests should usually move into the nearest domain contract module instead of staying standalone.

When merging, prefer moving tests unchanged first, then deduplicate helpers in a separate commit so failures remain easy to bisect.
