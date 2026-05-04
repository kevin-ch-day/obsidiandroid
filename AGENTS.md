# Agent instructions (repository-wide)

These notes apply to anyone editing this codebase (humans or automated agents).

## Project shape

- Primary language: **Python 3** (see `requirements.txt` for dependencies).
- **Pipeline entry:** `main.py` is the thin CLI shell; orchestration lives in `analysis/pipeline/runner.py` (`run_pipeline`). Tests may monkeypatch symbols on `main`; `analysis/pipeline/main_facade.py` bridges those patches into the runner. For scripts, prefer **`from obsidiandroid.pipeline import run_pipeline`** or **`from obsidiandroid.cli.pipeline_entry import run_pipeline`**; **`from utils.pipeline_entry import run_pipeline`** remains a compatibility alias. A short map of `stage_*` modules is in `analysis/pipeline/README.md`.
- **Src layout:** installable package code lives under **`src/obsidiandroid/`** (`cli`, `pipeline`, `common`, …). **`obsidiandroid.common`** holds hashing, canonicalization, path safety, runtime diagnostics paths, ML console verbosity gates, and the distribution printer; repo-root **`utils/`** shims re-export those modules for backward compatibility. Other `utils/` helpers remain during migration; see `STRUCTURE_MIGRATION_PLAN.md`.
- **Making `obsidiandroid` importable:** Prefer **`pip install -e .`** from the repo root. Without an editable install, use **`export PYTHONPATH="$PWD/src:$PYTHONPATH"`**, run **`./run.sh`** (which injects `src` automatically), or rely on **`tests/conftest.py`** prepending `src/` during **pytest**. Smoke-check: **`python scripts/dev/check_import_surface.py`** or **`make dev-import-check`**.
- Other entry points: `run.sh` / `utils/startup_menu.py` (`obsidiandroid` console script → `obsidiandroid.cli.startup_menu:main`), ML training under `ml_classification/`, database access under `database/`.
- **MySQL 8+** is assumed for cohort SQL that uses window functions (`ROW_NUMBER()`, etc.); see `database/cohort_sql_fragments.py`.
- **Database credentials:** `database/db_config.py` reads `OBSIDIAN_DB_*` environment variables; optional repo-root `.env` is loaded when `python-dotenv` is installed. For typed access in new code, use `database.settings.load_connection_settings()`. Before long runs or CI jobs that touch the DB, run `make preflight-db` or `python -m database.split_db_health`.

## Repository layout policy (hybrid migration)

- **`src/obsidiandroid/`** is the **canonical package surface** for **new public imports** (`obsidiandroid.cli`, `obsidiandroid.common`, `obsidiandroid.governance` where present, `obsidiandroid.pipeline` facade, etc.).
- Top-level **`analysis/`**, **`database/`**, **`ml_classification/`**, **`model/`**, and **`utils/`** are **transitional legacy implementation** trees kept for compatibility and existing tests. Do **not** relocate them without a **dedicated migration pass** and test updates.
- **New code** should **prefer `obsidiandroid.*`** wherever a canonical module or facade already exists; fall back to legacy paths only when no facade exists yet (see `STRUCTURE_MIGRATION_PLAN.md`).
- **`utils/` shims** (where present) must stay **thin re-exports**; **do not add new duplicated business logic** in shims—implement in `src/obsidiandroid/` and re-export.
- **`output/`** and **`logs/`** are **runtime-generated** state (gitignored), not source. Do not treat them as part of the package API.
- **`artifacts/baselines/`** is the **intentional** place for small preserved evidence / regression baselines (not ad-hoc run outputs under `output/`).
- **Dev / hygiene scripts** belong under **`scripts/dev/`** (e.g. import surface checks).
- **Diagnostic and operator inspection** scripts: see **`scripts/diagnostics/README.md`** for the index; most still live at **`scripts/*.py`** until a future move pass—new diagnostic scripts should follow that index and target living under the diagnostics area when practical.
- **Do not move** core domains such as **`analysis/pipeline`**, **`database/`**, **`ml_classification/`**, or **`model/`** as a drive-by—only with a planned pass and tests.

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

### Package / layout validation (src package + shims)

After changes that touch **`src/obsidiandroid/`**, **`utils/`** shims, or install layout, run:

```bash
python scripts/dev/check_import_surface.py
make dev-import-check
pytest -q -m "not slow"
```

The first two exercise editable-install / `PYTHONPATH` import paths; the last is the default fast test selection.

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
- Optionally run **`make ml-scan`** or **`python run_ml_static_scan.py`** to catch accidental `.predict()` misuse in ML code (add **`--strict`** to fail the command when warnings are found).

## User-facing documentation

- Update **README.md** (or other user docs) when behavior, commands, or setup steps visible to users change.
