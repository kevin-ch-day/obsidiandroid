# Developer Guide

This guide documents the day-to-day workflow for engineers extending ObsidianDroid's malware labeling and model training platform. It covers environment expectations, branching and review practices, validation requirements, and helpful tooling available in the repository.

## Environment Setup

1. **Clone the repository** and install dependencies:
   ```bash
   git clone <repository-url>
   cd obsidiandroid
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
2. **Optional tooling:**
   - Install `pre-commit` and run `pre-commit install` to mirror CI checks locally.
   - Install Docker if you plan to test database snapshots or run services in containers.

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
- Leverage utilities under `utils/` and `scripts/` instead of duplicating logic.

## Working with the Staged Pipeline

The runtime pipeline is now split into stage modules under `analysis/pipeline/`.

- Keep `main.py` orchestration-focused; add heavy logic in `stage_*.py` modules.
- Document stage entry/exit contracts in docstrings (input columns, required keys, and failure behavior).
- Preserve wrapper compatibility in `main.py` when moving existing helpers to stage modules.
- Add focused unit tests per stage module (for example: `tests/test_stage_<name>.py`) for success and integrity-failure paths.
- Use [`pipeline_staging_guide.md`](pipeline_staging_guide.md) as the primary extension checklist.

## Testing Expectations

- Unit tests live under `tests/`; add coverage for new features and bug fixes.
- Execute fast feedback commands before pushing:
  ```bash
  pytest -q
  python run_ml_static_scan.py  # optional static analysis for ML misuse
  python clean_bytecode_cache.py  # remove stale __pycache__ before committing
  ```
- For changes touching data pipelines, run representative integration tests or dry-run `main.py` with a small batch.
- Prefer adding stage-level tests before full end-to-end tests so failures are easier to localize.

## Data and Secrets Handling

- Request access to required database snapshots and VirusTotal replication tables from the data engineering team (see [`data_sources.md`](data_sources.md) for required schemas and refresh cadence).
- Store credentials securely using environment variables or secret managers. Never commit secrets to the repository.
- Use sample configuration templates in `config/` when sharing reproducible test cases.

## Tooling Reference

- **`scripts/rebuild_features.py`** – Regenerate feature matrices when schema changes.
- **`scripts/backfill_labels.py`** – Recompute labels for historical samples after rule updates.
- **`testing/` utilities** – Provide fixtures and synthetic datasets for isolated validation.
- **`run_tests.sh`** – Aggregates test execution and linting for CI parity.

## Release Checklist

1. Ensure the branch is up to date with `main` and all tests pass.
2. Update documentation in `doc/` when user-facing behavior changes.
3. Tag the release in Git once merged and update release notes with:
   - Summary of changes.
   - Required migrations or data refresh tasks.
   - Links to dashboards or playbooks impacted.
4. Coordinate with operations to schedule any downtime or data backfills.

Maintainers can adapt this checklist as processes evolve, but the structure provides a baseline for consistent, auditable releases.
