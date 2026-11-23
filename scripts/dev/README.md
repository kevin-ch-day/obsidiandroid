# Developer tooling (`scripts/dev/`)

Scripts here support **package layout, import hygiene, and local repo maintenance** — not production pipeline runs.

| Script / module | Purpose |
|-----------------|---------|
| [`check_import_surface.py`](check_import_surface.py) | Smoke-test `obsidiandroid` imports and shim parity; orchestrates static ratchets; exits nonzero on failure. |
| [`import_surface_policy.py`](import_surface_policy.py) | AST/file-system only: retired-root import scans, `# Filename:` header ratchet, and UTF-8 BOM scan (shared with tests). |
| [`check_doc_hygiene.py`](check_doc_hygiene.py) | Block known-removed phantom script paths in operator docs; **`make doc-check`**. |
| [`clean_bytecode_cache.py`](clean_bytecode_cache.py) | Remove `__pycache__`, local logs, and common junk under a tree including `.pytest_cache`, `.pytest_tmp*`, `.mypy_cache`, `.ruff_cache`, `htmlcov`, and coverage files (**canonical**; use `python scripts/dev/clean_bytecode_cache.py` or `make clean-bytecode`). |
| [`data_fuzzer.py`](data_fuzzer.py) | Synthetic classification data for stress tests (`sklearn` + pandas). |
| [`run_ml_static_scan.py`](run_ml_static_scan.py) | Argparse driver for the ML predict misuse scan (`python -m scripts.dev.run_ml_static_scan` or `make ml-scan`). |
| [`scan_ml_predict_misuse.py`](scan_ml_predict_misuse.py) | Core walker used by `run_ml_static_scan`. |
| [`output_writer_audit.py`](output_writer_audit.py) | Static CSV audit of output-writing call sites (`make output-writer-audit`). |
| [`build_canonical_slot_fixtures.py`](build_canonical_slot_fixtures.py) | Regenerate checked-in offline canonical-slot fixtures; maintainers only. |
| [`refresh_canonical_handoff.py`](refresh_canonical_handoff.py) | Refresh canonical handoff artifacts for existing canonical slots (`make refresh-canonical-handoff`). |
| [`validate_canonical_runs.py`](validate_canonical_runs.py) | Offline/live canonical closure artifact validation (`make verify-canonical`). |
| [`wait_validate_canonical_slot.py`](wait_validate_canonical_slot.py) | Wait for a canonical slot, then optionally refresh and validate it. |

### Shell entrypoints (Fedora venv, pytest)

| Script | Purpose |
|--------|---------|
| [`bootstrap_venv.sh`](bootstrap_venv.sh) | Create/refresh `.venv` and install `requirements.txt`; repo-root [`../../setup.sh`](../../setup.sh) delegates here. |
| [`checkout_venv.sh`](checkout_venv.sh) | Locate the local or primary checkout's `.venv` for the launcher, Makefile, and pytest wrappers. |
| [`launch_startup_menu.sh`](launch_startup_menu.sh) | Prepend local `src/` and invoke `python -m obsidiandroid.cli`. Repo-root [`../../run.sh`](../../run.sh) delegates here. |
| [`run_pytest.sh`](run_pytest.sh) | Run pytest with the selected Python and checkout import paths. |
| [`run_tests.sh`](run_tests.sh) | Fast pytest with the default options from `pyproject.toml`. |
| [`run_tests_changed.sh`](run_tests_changed.sh) | Map changes since the merge base, including local work, to fast tests. `make test-changed` defaults to `BASE=origin/main`. |
| [`run_tests_integration.sh`](run_tests_integration.sh) | Integration lane only; **`make test-integration`** / **`make verify-integration`**. |
| [`run_tests_pipeline_integration.sh`](run_tests_pipeline_integration.sh) | Full partial `run_pipeline` lane (`pipeline_heavy` marker); **`make verify-pipeline-integration`**. |
| [`run_tests_full.sh`](run_tests_full.sh) | Full pytest including `slow` modules; **`make test-full`** invokes this path. |

**`make test`**, **`make test-changed`**, **`make test-integration`**, and **`make test-full`** invoke these scripts directly (no repo-root wrappers).

**Pipeline preflight cost:**
- `OBSIDIANDROID_PREFLIGHT_SKIP_BACKLOG=1` — skip live backlog/debt DB snapshot during `run_pipeline` preflight.
- `OBSIDIANDROID_PREFLIGHT_REFRESH_BACKLOG=0` — keep snapshot lines but do not auto-refresh stale triage exports.
- Pytest already sets `OBSIDIANDROID_TEST_OUTPUT_ROOT`, which disables backlog preflight automatically in partial `run_pipeline()` tests.

Use **`make tree-root`** for one level, **`make tree-source`** for the checkout
tree, or **`make tree-obsidiandroid`** for the canonical Python package. These
targets use the `tree` utility.

Related **Makefile** shortcuts: **`make setup`** (→ **`./setup.sh`** / **`bootstrap_venv.sh`**), **`make menu`** (→ **`./run.sh`** / **`launch_startup_menu.sh`**), **`make install-editable`** (`pip install -e .`), **`make verify`** (this script + **`make test`**), **`make doc-check`**, **`make ci`** (same as **GitHub Actions**: **`doc-check`** + **`verify`** + **`ml-scan-strict`**).

From the repository root (after `pip install -e .` or `export PYTHONPATH="$PWD/src:$PYTHONPATH"`):

```bash
python scripts/dev/check_import_surface.py
make dev-import-check
```

See also [`docs/STRUCTURE_MIGRATION_PLAN.md`](../../docs/STRUCTURE_MIGRATION_PLAN.md) and [`docs/AGENTS.md`](../../docs/AGENTS.md).
