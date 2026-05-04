# Tests

- **`tests/` vs `devtools/`:** Pytest collects only this tree. Small QA helpers (synthetic fuzzer, `scan_ml_predict_misuse`) live in repo-root `devtools/`, not here.
- **Default run:** `pytest` / `make test` — respects `pytest.ini` (`-m "not slow"`). See `tests/conftest.py` for the `_SLOW_TEST_MODULES` list and temp output routing. Pytest basetemp is `.pytest_tmp/` at the repo root (gitignored).
- **Full run:** `make test-full` — includes slow integration modules (manifest, menus, heavy stages).
- **Policy:** add focused unit tests next to the code you change; register heavy modules in `_SLOW_TEST_MODULES` so the fast loop stays usable.

Run requirements are in the repo root `AGENTS.md` and `docs/developer_guide.md`.
