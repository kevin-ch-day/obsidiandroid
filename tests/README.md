# Tests

- **Default run:** `pytest` / `make test` — respects `pytest.ini` (`-m "not slow"`). See `tests/conftest.py` for the `_SLOW_TEST_MODULES` list and temp output routing.
- **Full run:** `make test-full` — includes slow integration modules (manifest, menus, heavy stages).
- **Policy:** add focused unit tests next to the code you change; register heavy modules in `_SLOW_TEST_MODULES` so the fast loop stays usable.

Run requirements are in the repo root `AGENTS.md` and `docs/developer_guide.md`.
