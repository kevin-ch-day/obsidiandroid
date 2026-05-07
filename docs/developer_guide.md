# Developer Guide

This guide documents the day-to-day workflow for engineers extending ObsidianDroid's malware labeling and model training platform. It covers environment expectations, branching and review practices, validation requirements, and helpful tooling available in the repository.

## Environment Setup

1. **Clone the repository** and install dependencies. Either use the bundled Fedora-oriented script or a manual venv:
   ```bash
   git clone <repository-url>
   cd obsidiandroid
   ./setup.sh
   # or: make setup   # same as ./setup.sh
   source .venv/bin/activate
   make install-editable
   ```
   **Manual** alternative:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   pip install -e .
   ```
2. **Optional tooling:**
   - Install `pre-commit` and run `pre-commit install` to use **`.pre-commit-config.yaml`** (basic whitespace/YAML checks; complements **`make verify`**).
   - Install Docker if you plan to test database snapshots or run services in containers.
   - Install `tree` if you want **`make tree-source`** (filtered repository layout; run **`make clean-bytecode`** first to drop stray caches).

### Continuous integration

GitHub Actions runs **`make verify`** and **`make ml-scan-strict`** on pushes to **`main`**, on pull requests, and on **workflow dispatch** (see **`.github/workflows/ci.yml`**). The job uses a **Python 3.10 / 3.12** matrix, **`pip check`** after install, and **`contents: read`** permissions. Run **`make ci`** locally for the same gates. Dependabot bumps **GitHub Actions** monthly and **`requirements.txt`** weekly (see **`.github/dependabot.yml`**).

### Importing the `obsidiandroid` package (`src/` layout)

Optional: if you use **pyenv** or **asdf**, see repo-root **`.python-version`** (**`3.12`**, aligned with CI). Supported interpreters follow **`pyproject.toml`** **`requires-python`** (currently **≥ 3.10**).

Canonical library code under **`src/obsidiandroid/`** should be importable as **`obsidiandroid`**. Recommended setups:

- **Preferred:** after dependencies, run **`pip install -e .`** from the repository root so imports work in any working directory without manual `PYTHONPATH`.
- **Checkout-only fallback:** **`export PYTHONPATH="$PWD/src:$PYTHONPATH"`** (adjust for your shell).
- **`./run.sh`** sets **`PYTHONPATH=<repo>/src:…`** before invoking Python so the interactive menu works without an editable install.
- **`pytest`** prepends **`repo/src`** in **`tests/conftest.py`** so tests resolve **`obsidiandroid`** without extra env vars.

Quick sanity check: **`python scripts/dev/check_import_surface.py`** or **`make dev-import-check`**.

## Branching and Code Reviews

- Create topic branches from `main` for each change.
- Keep commits focused; include descriptive messages summarizing intent and context.
- Open pull requests early and link to relevant issues or tickets.
- Request review from a maintainer familiar with the affected subsystem (data ingestion, modeling, or tooling).
- Address review feedback promptly and avoid force-pushing over reviewed commits unless requested.

## Coding Conventions

- Follow repository-wide PEP 8 guidelines and prefer type hints for new Python modules.
- Add Google-style docstrings to public modules, classes, and functions.
- Keep configuration defaults in `config/` and avoid hard-coded secrets or paths.
- Leverage canonical helpers under `obsidiandroid.*` and operational tools under `scripts/` instead of duplicating logic; use `utils/` only for compatibility shim work.

## Working with the Staged Pipeline

Orchestration lives in **`src/obsidiandroid/pipeline/runner.py`** (`run_pipeline`). Legacy **`analysis.pipeline.runner`** is an identity shim to the same module. **`main.py`** is a thin CLI shell + compatibility surface; tests may monkeypatch `main` symbols which are bridged into the runner via the legacy `analysis/pipeline/main_facade.py` shim.

- Add heavy logic in `stage_*.py` modules, not in `runner.py`.
- Document stage entry/exit contracts in docstrings (input columns, required keys, and failure behavior).
- Scripts that need the full pipeline should use **`from obsidiandroid.pipeline import run_pipeline`**, **`from obsidiandroid.cli.pipeline_entry import run_pipeline`**, or the legacy aliases **`from utils.pipeline_entry import run_pipeline`** / **`from main import run_pipeline`**; avoid importing deep `stage_*` internals unless you are extending a stage.
- Add focused unit tests per stage module (for example: `tests/test_stage_<name>.py`) for success and integrity-failure paths.
- Use [`pipeline_staging_guide.md`](pipeline_staging_guide.md) as the primary extension checklist.

## Testing Expectations

- Default pytest options (fast run, `slow` marker, basetemp) are in **`pyproject.toml`** `[tool.pytest.ini_options]`.
- Unit tests live under `tests/` (see [`tests/README.md`](../tests/README.md) for slow markers and layout); add coverage for new features and bug fixes.
- Execute fast feedback commands before pushing:
  ```bash
  pytest -q
  python -m scripts.dev.run_ml_static_scan  # optional static analysis for ML misuse
  python scripts/dev/clean_bytecode_cache.py  # remove stale __pycache__ before committing
  ```
- For changes touching data pipelines, run representative integration tests or dry-run `main.py` with a small batch.
- Prefer adding stage-level tests before full end-to-end tests so failures are easier to localize.

## Data and Secrets Handling

- Request access to required database snapshots and VirusTotal replication tables from the data engineering team (see [`data_sources.md`](data_sources.md) for required schemas and refresh cadence).
- Store credentials securely using environment variables or secret managers. Never commit secrets to the repository.
- Use sample configuration templates in `config/` when sharing reproducible test cases.

## Makefile quick reference

| Target | Purpose |
| --- | --- |
| `make setup` | Create/refresh `.venv` and `pip install -r requirements.txt` (see `setup.sh`). |
| `make menu` | Launch the interactive menu (`run.sh`; sets `PYTHONPATH=src`). |
| `make install-editable` | `pip install -e .` (run inside the venv). |
| `make test` / `make test-full` | Fast or full pytest (see `pyproject.toml` defaults). |
| `make dev-import-check` | Import surface smoke test for `obsidiandroid` and shims. |
| `make doc-check` | Fails if operational docs reintroduce removed phantom paths (`scripts/dev/check_doc_hygiene.py`). |
| `make verify` | Runs `dev-import-check` logic then **fast** pytest (same as `make test` after import smoke). |
| `make ci` | **`make doc-check`**, then **`make verify`**, then **`make ml-scan-strict`** — matches **`.github/workflows/ci.yml`**. |
| `make ml-scan-strict` | ML call-site scan; fails on any warning (stricter than `make ml-scan`). |
| `make clean-bytecode` | Remove `__pycache__` and common junk under the repo root. |
| `make tree-source` | Print a filtered repo-root tree (requires `tree` on `PATH`). |
| `make tree-obsidiandroid` | **`src/obsidiandroid/`** only — see canonical package growth vs legacy `utils/`. |
| `make tree-utils` | **`utils/`** tree (compatibility shims and bootstrap wrappers). |
| `make tree-exporting-shims` | **`utils/exporting/`** thin re-exports only. |
| `make ml-scan` | Static scan for suspicious `.predict()` / `.predict_proba()` use. |
| `make preflight-db` | MySQL/MariaDB connectivity check before long DB-backed runs. |

## Tooling Reference

- **`scripts/README.md`** – How to run operator scripts from the repo root and DB preflight expectations.
- **`scripts/backfill_permission_trends_warehouse.py`** – Warehouse backfills when configured.
- **`scripts/research/`** – Publication tables, evidence bundles, structural diagnostics.
- **`scripts/dev/`** – Synthetic dataset fuzzer, ML static-scan, venv/test wrappers (not collected by pytest; see `tests/` for automated tests). Legacy **`devtools/`** at repo root was removed.
- **`scripts/dev/run_tests.sh`** / **`Makefile`** – Fast (`make test`) and full (`make test-full`) pytest; **`make preflight-db`** checks MySQL connectivity (`database.split_db_health`).

## Release Checklist

1. Ensure the branch is up to date with `main` and all tests pass.
2. Update documentation in `docs/` when user-facing behavior changes.
3. Tag the release in Git once merged and update release notes with:
   - Summary of changes.
   - Required migrations or data refresh tasks.
   - Links to dashboards or playbooks impacted.
4. Coordinate with operations to schedule any downtime or data backfills.

Maintainers can adapt this checklist as processes evolve, but the structure provides a baseline for consistent, auditable releases.
