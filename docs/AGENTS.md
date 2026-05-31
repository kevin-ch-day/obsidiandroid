# Agent instructions (repository-wide)

These notes apply to anyone editing this codebase (humans or automated agents).

The repo root keeps a short **[`AGENTS.md`](../AGENTS.md)** stub so tools that expect that path still find this document.

## Project shape

- Primary language: **Python 3** (see `requirements.txt` for dependencies).
- **Pipeline entry:** `main.py` is the thin CLI shell (prepends `./src` for checkout installs); **`run_pipeline`** is implemented in **`obsidiandroid.pipeline.runner`** (**Pass 67**); **`analysis.pipeline.runner`** is an identity shim to the same module. **Stage modules** (`stage_*`, AV/vendor chain, permission-trends report, manifest, …) are implemented under **`obsidiandroid.pipeline`** (**Passes 68–71, 74**); **`analysis.pipeline.stage_*`** on disk are identity shims—see **`analysis/pipeline/README.md`** for the index. Tests may monkeypatch symbols on `main`; `analysis/pipeline/main_facade.py` bridges those patches into the runner. For scripts, use **`from obsidiandroid.pipeline import run_pipeline`** or **`from obsidiandroid.cli.pipeline_entry import run_pipeline`**.
- **Src layout:** installable package code lives under **`src/obsidiandroid/`** (`cli`, `pipeline`, `common`, `reporting`, `governance`, **`observability`** — **`logging`** + **`pipeline_observability`** for pipeline run narration — **`diagnostics`**, …). **`obsidiandroid.common`** holds hashing, canonicalization, path safety, **output path layout** (**`output_paths`**), runtime diagnostics paths, ML console verbosity gates, the distribution printer, and **export** helpers (**`export_naming`**, **`export_vendor_raw`**, **`export_workbook`**). **Excel / vendor / confusion-matrix export orchestration** is in **`obsidiandroid.reporting.export_manager`**. **Structured file logging and runtime tee logging** live in **`obsidiandroid.observability.logging`** (submodules **`logger`** / **`runtime`**); you may also use **`from obsidiandroid.observability import get_logger, log_event`**. **Pipeline observability** (JSONL timeline, stage summary, finalize, run health) is **`obsidiandroid.observability.pipeline_observability`** only — do not use removed **`analysis.observability`**. **`obsidiandroid.diagnostics`** is the canonical home for run diagnostics (`output_inventory`, `output_artifact_policy`, `research_validity`, `hostile_audit`, …). See [`STRUCTURE_MIGRATION_PLAN.md`](STRUCTURE_MIGRATION_PLAN.md) for the remaining shim surfaces still on disk.
- **Making `obsidiandroid` importable:** Prefer **`pip install -e .`** from the repo root (shortcut: **`make install-editable`** with the venv active). Without an editable install, use **`export PYTHONPATH="$PWD/src:$PYTHONPATH"`**, run **`./run.sh`** or **`make menu`** (which injects `src` automatically), or rely on **`tests/conftest.py`** prepending `src/` during **pytest**. Initial venv + requirements: **`./setup.sh`** or **`make setup`**. Smoke-check: **`python scripts/dev/check_import_surface.py`** or **`make dev-import-check`**.
- Other entry points: `run.sh` / **`python -m obsidiandroid.cli.startup_menu`** (`obsidiandroid` console script → `obsidiandroid.cli.startup_menu:main`), ML training under **`obsidiandroid.modeling`**, and **database:** every module on the **`obsidiandroid.database`** façade (connection, engine, sample metadata, AV Tier D helpers, utilities, split health, plus optional helper modules) is **canonical under `src/obsidiandroid/database/`**. Repo-root **`database/`** is now reduced to the package compatibility root plus **`split_db_health`** (which also supports **`python -m database.split_db_health`**). The ordered façade name list and derived legacy-shim parity tuples live in **`obsidiandroid.database.facade_manifest`** (single source for package bootstrap and import checks). **Canonical DB imports** use **`obsidiandroid.database`**. Avoid ad-hoc re-exports beyond the façade.
- **MySQL 8+** is assumed for cohort SQL that uses window functions (`ROW_NUMBER()`, etc.); see **`obsidiandroid.database.cohort_sql_fragments`**.
- **Database credentials:** **`obsidiandroid.database.db_config`** reads **`OBSIDIAN_DB_*`** environment variables; optional repo-root `.env` is loaded when **`python-dotenv`** is installed. For typed access in new code, use **`obsidiandroid.database.settings.load_connection_settings()`**. Before long runs or CI jobs that touch the DB, run **`make preflight-db`** or **`python -m database.split_db_health`**.

## Repository layout policy (hybrid migration)

- **`src/obsidiandroid/`** is the **canonical package surface** for **new public imports** (`obsidiandroid.cli`, `obsidiandroid.common`, `obsidiandroid.governance`, `obsidiandroid.observability`, `obsidiandroid.pipeline` facade, etc.).
- Top-level **`analysis/`** now effectively means the **final `analysis/pipeline/` compatibility shell**: **`analysis/pipeline/__init__.py`**, **`runner.py`**, **`main_facade.py`**, and the README. Nested legacy imports such as **`analysis.pipeline.manifest.writer`** or **`analysis.pipeline.governance.policy`** are now registered as compatibility aliases from the pipeline package root rather than by physical nested shim files on disk. Repo-root **`database/`** now exists only for the package compatibility root and the retained **`split_db_health`** entrypoint (implementations under **`src/obsidiandroid/database/`**). Repo-root **`utils/`**, **`model/`**, and **`ml_classification/`** were **removed** — use **`obsidiandroid.*`** (contracts under **`obsidiandroid.vendors.contracts`**, risk-band config under **`obsidiandroid.risk_band`**). Do **not** relocate or delete remaining legacy roots without a **dedicated migration pass** and test updates.
- **New code** should **prefer `obsidiandroid.*`** wherever a canonical module or facade already exists; fall back to legacy paths only when no facade exists yet (see [`STRUCTURE_MIGRATION_PLAN.md`](STRUCTURE_MIGRATION_PLAN.md)). **Pass 31:** pipeline/DB/ML implementation imports **`obsidiandroid.cli.ui.display`** and **`obsidiandroid.common.ml_console`** directly.
- **Import-surface enforcement:** `scripts/dev/check_import_surface.py` runs import smoke plus static ratchets defined in **`scripts/dev/import_surface_policy.py`** (no `importlib` of project packages there). Those checks fail when canonical `src/` code or normal `scripts/` import legacy compatibility roots (`analysis`, `ml_classification`), when non-parity tests import those roots directly (except explicit shim/parity fixtures), when canonical `src/` modules keep stale ``# Filename:`` headers (first path segment names `analysis`, `ml_classification`, or repo-root `database/`), or when non-`__init__` legacy leaves under `analysis/` are not thin `sys.modules` identity shims. UTF-8 BOM prefixes on tracked-style `*.py` trees are also rejected. The check script itself is exempt from the legacy-root import scan because it deliberately imports legacy paths to verify shim identity.
- **`output/`** and **`logs/`** are **runtime-generated** state (gitignored), not source. Do not treat them as part of the package API.
- **`artifacts/baselines/`** is the **intentional** place for small preserved evidence / regression baselines (not ad-hoc run outputs under `output/`).
- **Paper cohort identity:** the active manuscript-facing locked benchmark is the immutable **`20260504T044304Z__8c64e6`** lock (`1226` samples / `39` families / `6` malware types) resolved from **`artifacts/baselines/20260504T044304Z__8c64e6/cohort_lock_manifest.json`**. The later **`20260526T021235Z__8b6966`** `1187`-sample rebaseline is **archival drift evidence only**, not the active paper contract.
- **Dev / hygiene** tooling lives under **`scripts/dev/`** (import checks, ML scan, bytecode clean, and shell helpers: venv bootstrap, startup menu launcher, fast/full pytest). Repo-root **`setup.sh`** and **`run.sh`** delegate to **`scripts/dev/`**; **`make test`** / **`make test-full`** invoke **`scripts/dev/run_tests.sh`** and **`run_tests_full.sh`** directly.
- **Diagnostic and operator inspection** scripts: canonical modules live under **`scripts/diagnostics/`** (see **`scripts/diagnostics/README.md`**). Legacy repo-root packages **`data_inspect`** and **`devtools`** were **removed** — import **`scripts.diagnostics.*`** and **`scripts.dev.*`** (Pass 24 in **`STRUCTURE_MIGRATION_PLAN.md`**).
- **Paper census / drift audit exports:** use **`python scripts/diagnostics/export_cohort_census.py --output-dir paper_exports/docs`** for canonical paper-facing cohort census and gate-matrix artifacts, and **`python scripts/diagnostics/audit_locked_cohort_gap.py`** for the focused locked-vs-live gap audit. These exporters should be preferred over ad-hoc SQL approximations when answering manuscript cohort questions.
- **Misc scripts:** some operators still live at **`scripts/*.py`** until a future move pass—new diagnostic scripts should follow the diagnostics index when practical.
- **Do not move** core domains such as **`analysis/pipeline`** or **`database/`** as a drive-by—only with a planned pass and tests. **Note:** `analysis/pipeline` remains on disk primarily for **import compatibility** (thin shims); substantive pipeline code belongs in **`obsidiandroid.pipeline`**.

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

Runs pytest with **`-m "not slow"`** (configured in **`pyproject.toml`** → `[tool.pytest.ini_options]`). Suitable for everyday development and tight feedback.

Use **one** of:

- `./scripts/dev/run_tests.sh`
- `make test`
- `pytest -q` (honours `addopts` in `[tool.pytest.ini_options]`)

### Package / layout validation (src package + shims)

After changes that touch **`src/obsidiandroid/`**, legacy root shims (**`analysis/`**), or install layout, run:

```bash
make verify
# or, separately:
python scripts/dev/check_import_surface.py
make dev-import-check
pytest -q -m "not slow"
```

**`make verify`** runs **`scripts/dev/check_import_surface.py`** and then the same fast pytest selection as **`make test`** (import paths + default **`slow`** exclusion).

**CI:** Pushes to **`main`** and pull requests run **`make doc-check`**, **`make verify`**, and **`make ml-scan-strict`** in GitHub Actions. Locally, **`make ci`** matches that pipeline (doc guardrails + import smoke + fast tests + strict ML scan).

Whole test **files** listed in `_SLOW_TEST_MODULES` inside `tests/conftest.py` are auto-marked `slow` at collection time so they stay out of the default run.

### Full suite (integration-heavy)

Runs **all** tests, including `slow` modules (manifest, startup menu, permission trends, trainers, etc.):

- `./scripts/dev/run_tests_full.sh`
- `make test-full`
- `pytest -q -m "slow or not slow"`

Use before releases or when changing behavior covered only by slow modules.

### Adding tests

- Add or extend tests for bug fixes and new behavior.
- Prefer **narrow unit tests** in modules that are not in `_SLOW_TEST_MODULES` so `pytest` stays fast.
- Reserve **`slow`** for expensive integration: add the module name to `_SLOW_TEST_MODULES`, or mark individual tests with `@pytest.mark.slow` when appropriate.

## Hygiene before commit

- Keep **`pyproject.toml`** `[tool.setuptools.packages.find] include` aligned with real top-level packages (remove stale entries like a non-existent `testing/` tree) so editable installs do not claim empty namespaces.
- Run **`python scripts/dev/clean_bytecode_cache.py`** (or **`make clean`** / **`make clean-bytecode`**, which invoke the same script) to drop `__pycache__` and stray log artifacts where relevant. When reviewing repo layout, prefer **`make tree-source`** after cleanup (filters generated dirs; requires the **`tree`** CLI unless you only need **`make help`** guidance).
- When changing anything that hits MySQL, run **`make preflight-db`** (or `python -m database.split_db_health`) with valid `OBSIDIAN_DB_*` / `.env` settings.
- Optionally run **`make ml-scan`** or **`python -m scripts.dev.run_ml_static_scan`** to catch accidental `.predict()` misuse in ML code (add **`--strict`** to fail the command when warnings are found).

## User-facing documentation

- Update **README.md** (or other user docs) when behavior, commands, or setup steps visible to users change.
