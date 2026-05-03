# Agent instructions (repository-wide)

These notes apply to anyone editing this codebase (humans or automated agents).

## Project shape

- Primary language: **Python 3** (see `requirements.txt` for dependencies).
- **Pipeline entry:** `main.py` is the thin CLI shell; orchestration lives in `analysis/pipeline/runner.py` (`run_pipeline`). Tests may monkeypatch symbols on `main`; `analysis/pipeline/main_facade.py` bridges those patches into the runner. For scripts, `from utils.pipeline_entry import run_pipeline` is a stable alias. A short map of `stage_*` modules is in `analysis/pipeline/README.md`.
- Other entry points: `run.sh` / `utils/startup_menu.py` (`obsidiandroid` console script), ML training under `ml_classification/`, database access under `database/`.
- **MySQL 8+** is assumed for cohort SQL that uses window functions (`ROW_NUMBER()`, etc.); see `database/cohort_sql_fragments.py`.
- **Database credentials:** `database/db_config.py` reads `OBSIDIAN_DB_*` environment variables; optional repo-root `.env` is loaded when `python-dotenv` is installed. For typed access in new code, use `database.settings.load_connection_settings()`. Before long runs or CI jobs that touch the DB, run `make preflight-db` or `python -m database.split_db_health`.

## Code style

- Follow [PEP 8](https://peps.python.org/pep-0008/).
- Prefer descriptive names and type hints where they clarify contracts.
- Use **Google-style docstrings** for public modules, classes, and functions.
- **Paths:** use forward slashes (`"output/diagnostics"`) or `pathlib.Path` / `os.path.join`. In Python, Windows-style backslashes in string literals (e.g. `"output\\diagnostics"`) are **not** a nested path on Linux or macOS — they create a single directory name containing a backslash, which is almost never what you want.

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
- When changing anything that hits MySQL, run **`make preflight-db`** (or `python -m database.split_db_health`) with valid `OBSIDIAN_DB_*` / `.env` settings.
- Optionally run **`python run_ml_static_scan.py`** to catch accidental `.predict()` misuse in ML code.

## User-facing documentation

- Update **README.md** (or other user docs) when behavior, commands, or setup steps visible to users change.
