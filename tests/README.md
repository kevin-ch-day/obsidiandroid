# Tests

- **`tests/` vs QA helpers:** Pytest collects only this tree. Canonical QA helpers (synthetic fuzzer, ML predict scan) live under **`scripts.dev`** (`scripts/dev/` on disk). Example: **`from scripts.dev import data_fuzzer`** or **`python scripts/dev/data_fuzzer.py`**.
- **Default run:** `pytest` / `make test` — respects **`pyproject.toml`** `[tool.pytest.ini_options]` (`-m "not slow"`). See `tests/conftest.py` for the `_SLOW_TEST_MODULES` list and temp output routing. Pytest basetemp is `.pytest_tmp/` at the repo root (gitignored).
- **Full run:** `make test-full` — includes slow integration modules (manifest, menus, heavy stages).
- **Policy:** add focused unit tests next to the code you change; register heavy modules in `_SLOW_TEST_MODULES` so the fast loop stays usable.

Contributor/agent notes: **[`docs/AGENTS.md`](../docs/AGENTS.md)** (repo-root `AGENTS.md` points there). See also **`docs/developer_guide.md`**.
