# Agent instructions (repository-wide)

These notes apply to anyone editing this codebase (humans or automated agents).

## Project shape

- Primary language: **Python 3** (see `requirements.txt` for dependencies).
- Entry points include CLI/menu flows (`run.sh`, `utils/startup_menu.py`), analysis pipelines under `analysis/`, ML training under `ml_classification/`, and database access under `database/`.
- **MySQL 8+** is assumed for cohort SQL that uses window functions (`ROW_NUMBER()`, etc.); see `database/cohort_sql_fragments.py`.

## Code style

- Follow [PEP 8](https://peps.python.org/pep-0008/).
- Prefer descriptive names and type hints where they clarify contracts.
- Use **Google-style docstrings** for public modules, classes, and functions.

## Scope of changes

- Keep edits **focused** on the requested task; avoid drive-by refactors or unrelated files.
- Match existing patterns (imports, logging, SQL construction) in touched modules.

## Testing

Install dependencies first:

```bash
pip install -r requirements.txt
```

### Default (fast loop)

Runs pytest with **`-m "not slow"`** (see `pytest.ini`). Suitable for everyday development and tight feedback.

Use **one** of:

- `./run_tests.sh`
- `make test`
- `pytest -q` (honours `addopts` in `pytest.ini`)

Whole test **files** listed in `_SLOW_TEST_MODULES` inside `tests/conftest.py` are auto-marked `slow` at collection time so they stay out of the default run.

### Full suite (integration-heavy)

Runs **all** tests, including `slow` modules (manifest, startup menu, permission trends, trainers, etc.):

- `./run_tests_full.sh`
- `make test-full`
- `pytest -q -m "slow or not slow"`

Use before releases or when changing behavior covered only by slow modules.

### Adding tests

- Add or extend tests for bug fixes and new behavior.
- Prefer **narrow unit tests** in modules that are not in `_SLOW_TEST_MODULES` so `pytest` stays fast.
- Reserve **`slow`** for expensive integration: add the module name to `_SLOW_TEST_MODULES`, or mark individual tests with `@pytest.mark.slow` when appropriate.

## Hygiene before commit

- Run **`python clean_bytecode_cache.py`** (or `make clean`) to drop `__pycache__` and stray log artifacts where relevant.
- Optionally run **`python run_ml_static_scan.py`** to catch accidental `.predict()` misuse in ML code.

## User-facing documentation

- Update **README.md** (or other user docs) when behavior, commands, or setup steps visible to users change.
