# Tests

- **`tests/` vs QA helpers:** Pytest collects only this tree. Canonical QA helpers (synthetic fuzzer, ML predict scan) live under **`scripts.dev`** (`scripts/dev/` on disk). Example: **`from scripts.dev import data_fuzzer`** or **`python scripts/dev/data_fuzzer.py`**.
- **Default run:** `pytest` / `make test` — respects **`pyproject.toml`** `[tool.pytest.ini_options]` (`-m "not (slow or integration or heavy or contract)"`). See `tests/conftest.py` for the `_SLOW_TEST_MODULES` list and temp output routing. Pytest basetemp is `.pytest_tmp/` at the repo root (gitignored).
- **Changed-files loop:** `make test-changed` (or `./scripts/dev/run_tests_changed.sh origin/main`) — runs only mapped `tests/test_*.py` modules touched in the git diff; falls back to import smoke when no tests map cleanly.
- **Integration lane:** `make test-integration` / `make verify-integration` — partial `run_pipeline()` and subprocess smoke tests (`test_main_runtime_overrides.py`, `test_pipeline_ablation_resilience.py`, `test_small_smoke.py`, …). Excluded from the default fast loop to keep local/CI verify under ~20 minutes.
- **Pipeline-heavy lane:** `make test-pipeline-integration` / `make verify-pipeline-integration` — seven full partial `run_pipeline()` failure-path tests marked `pipeline_heavy` (~50s each). CI runs this lane only when pipeline paths change (always on `main` pushes).
- **Full run:** `make test-full` — overrides the default marker filter and runs the entire suite.
- **Marker policy:** keep the fast loop focused on cheap logic and narrow contracts. Use `slow` for whole expensive modules, `contract` for broad deterministic governance/report/manifest checks, `integration` for stage/menu/report contracts with notable orchestration cost, and `heavy` for plotting/export or similar especially expensive checks.

Contributor/agent notes: **[`docs/AGENTS.md`](../docs/AGENTS.md)** (repo-root `AGENTS.md` points there). See also **`docs/developer_guide.md`**.

## Suite maintenance

Keep test ownership aligned to the canonical production domain; do not retain a
standalone file merely because a shim or migration once existed. Compatibility
tests belong in `test_legacy_shim_parity.py` or
`test_import_surface_guardrails.py`; immutable paper-lock and canonical fixtures are
regression assets, not general cleanup candidates.

Avoid recording static suite counts here: they become stale quickly. To inspect
the current shape, run:

```bash
find tests -name 'test_*.py' | wc -l
python -m pytest --collect-only -q
```

When consolidating narrow tests, move assertions unchanged into the nearest
domain contract first, then deduplicate helpers in a separate change. Keep the
fast lane inexpensive; use `contract`, `integration`, `heavy`, or `slow` for
expensive coverage. The production-wheel boundary is a `contract` test in
`test_obsidiandroid_package_surface.py`, so release packaging can be checked
explicitly without slowing ordinary local work.
