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

GitHub Actions runs a fast job (**`make doc-check`**, **`make verify`**, and
**`make ml-scan-strict`**) on Python 3.11 and 3.12, plus an unconditional
canonical-closure job on 3.12. The integration and heavier pipeline-integration
jobs run for relevant pull-request paths and on main pushes/workflow dispatch
(see **`.github/workflows/ci.yml`**). The fast job also runs **`pip check`**
after install and uses **`contents: read`** permissions. Locally,
**`make ci-fast`** covers the fast job; **`make ci`** adds canonical closure.
Run **`make verify-integration`** or **`make verify-pipeline-integration`** for
changes that affect those lanes. Dependabot bumps GitHub Actions monthly and
`requirements.txt` weekly (see **`.github/dependabot.yml`**).

### Importing the `obsidiandroid` package (`src/` layout)

Optional: if you use **pyenv** or **asdf**, see repo-root **`.python-version`** (**`3.12`**, aligned with CI). Supported interpreters follow **`pyproject.toml`** **`requires-python`** (currently **≥ 3.11**).

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
- Leverage canonical helpers under `obsidiandroid.*` and operational tools under `scripts/` instead of duplicating logic.
- When documenting outputs or debugging completed runs, prefer run-scoped artifacts under `output/runs/<run_id>/` and treat `run_evidence_index.md` plus `diagnostics/run_observability_summary.json` as the primary human + machine entrypoints.

## Working with the Staged Pipeline

Orchestration lives in **`src/obsidiandroid/pipeline/runner.py`** (`run_pipeline`). **`main.py`** is a thin CLI shell + compatibility surface; tests may monkeypatch `main` symbols, which are resolved by `obsidiandroid.cli.main_override_bridge`.

- Add heavy logic in **`obsidiandroid.pipeline`** `stage_*.py` modules under `src/obsidiandroid/pipeline/`, not in `runner.py`.
- Document stage entry/exit contracts in docstrings (input columns, required keys, and failure behavior).
- Scripts that need the full pipeline should use **`from obsidiandroid.pipeline import run_pipeline`**; avoid importing deep `stage_*` internals unless you are extending a stage.
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
| `make ci-fast` | **`make doc-check`**, **`make verify`**, then **`make ml-scan-strict`** — matches the CI fast job. |
| `make ci` | `make ci-fast` plus **`make verify-canonical`**; integration lanes are separate targets. |
| `make verify-integration` / `make verify-pipeline-integration` | Run the partial or heavier pipeline integration lane for matching changes. |
| `make ml-scan-strict` | ML call-site scan; fails on any warning (stricter than `make ml-scan`). |
| `make clean-bytecode` | Remove `__pycache__` and common junk under the repo root. |
| `make tree-source` | Print a filtered repo-root tree (requires `tree` on `PATH`). |
| `make tree-obsidiandroid` | **`src/obsidiandroid/`** only — canonical package tree. |
| `make tree-utils` | Stub (**`utils/`** removed — see `Makefile`). |
| `make tree-exporting-shims` | Stub (export helpers live under **`obsidiandroid.common`**). |
| `make ml-scan` | Static scan for suspicious `.predict()` / `.predict_proba()` use. |
| `make preflight-db` | MySQL/MariaDB connectivity check before long DB-backed runs. |

The scanner uses Python syntax to exclude literal source examples and recognizes
a local sklearn pipeline saved in a `joblib` dictionary and restored from its
`model` member at the same path. Unknown loads, whole dictionaries, reassignment
and ambiguous branch state retain warnings. This is a static heuristic, not a
model-artifact validation or a reason to load an untrusted pickle. Historical
experiment code need not be renamed to satisfy the scanner.

## Tooling Reference

- **`scripts/README.md`** – How to run operator scripts from the repo root and DB preflight expectations.
- **`scripts/maintenance/backfill_permission_trends_warehouse.py`** – Warehouse backfills when configured.
- **`scripts/research/`** – Publication tables, evidence bundles, structural diagnostics.
- **`scripts/dev/`** – Synthetic dataset fuzzer, ML static-scan, venv/test wrappers (not collected by pytest; see `tests/` for automated tests). Legacy **`devtools/`** at repo root was removed.
- **`scripts/dev/run_tests.sh`** / **`Makefile`** – Fast (`make test`) and full (`make test-full`) pytest; **`make preflight-db`** checks MySQL connectivity (`obsidiandroid.database.split_db_health`).

## Release Checklist

1. Ensure the branch is up to date with `main` and all tests pass.
2. Update documentation in `docs/` when user-facing behavior changes.
3. Tag the release in Git once merged and update release notes with:
   - Summary of changes.
   - Required migrations or data refresh tasks.
   - Links to dashboards or playbooks impacted.
4. Coordinate with operations to schedule any downtime or data backfills.

Maintainers can adapt this checklist as processes evolve, but the structure provides a baseline for consistent, auditable releases.

### Retired compatibility entry points

Unused Python wrappers were pruned after checking repository callers. Use the
canonical APIs in new code and in any local scripts that still import old names:

| Retired API | Canonical replacement |
| --- | --- |
| `cohort_reproducibility.apply_cohort_lock` | `apply_analysis_snapshot_lock`; pass `fail_closed=True` when strict evidence policy requires it |
| `cohort_reproducibility.export_cohort_snapshot` | `export_analysis_snapshot` |
| `finalize.patch_observability_scientific_adequacy_from_dataset_foundation` | `patch_observability_post_operator_artifacts` |
| `ledger_remediation.physical_schema_verification_hash` | `structural_digest.package_structural_digest` |
| `ledger_remediation.expected_table_digest_from_sql` | `structural_digest.expected_structural_digest_from_sql` |
| `ledger_remediation.live_table_digest` | `structural_digest.live_structural_digest` |
| `ledger_remediation.compare_table_digests` | `structural_digest.compare_structural_digests` |

The `physical_schema_verification_hash` field in historical receipts remains
supported; only the unused function with that name was removed. Historical
research-packet readers, permission-lane interpretation and immutable audit
artifacts remain supported. Local test runs of legacy menu/reporting code must
isolate real database connections; those views can still request live readiness
counts unless explicitly guarded.

Further cleanup removes legacy argument guessing and retries:

- `build_classification_row` now requires optional inputs by keyword. In
  particular, pass `records_by_vendor=...`; the sixth positional argument is no
  longer guessed to mean vendor records rather than a label-name map.
- Classification builders no longer retry `TypeError` with label mapping,
  sample-index and resolution context omitted. Existing failed-sample reporting
  records the error instead.
- Publication-export checks always pass their selected `output_root`; checker
  errors propagate rather than retrying against the configured default root.
- Import `display_post_training_metrics` from
  `obsidiandroid.modeling.model_evaluation`, its canonical implementation.
- The unused `LANE_OEM_OR_GOOGLE` Python constant is removed. Current reporting
  uses separate OEM and Google lanes; historical `oem_or_google` migration
  metadata remains intact.

Reporting and diagnostic failure paths also use current APIs:

- Banker-family pattern clustering uses the pinned sklearn `metric` interface.
  Constructor or clustering failures propagate; the report no longer invents
  row-number-based cluster assignments on failure. Previously written report
  artifacts are not erased, and historical cluster artifacts are not rewritten.
- Vendor parsers receive `(label, metadata)`. Internal `TypeError` is counted as a
  parser error rather than retried as a one-argument parser. The existing generic
  diagnostic fallback is retained and explicitly counted and identified in the UI.
- Workbook loaders receive `emit_warnings=False`; internal failures propagate
  without a second call that could obscure the error or change warning behavior.
