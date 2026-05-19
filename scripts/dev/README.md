# Developer tooling (`scripts/dev/`)

Scripts here support **package layout, import hygiene, and local repo maintenance** — not production pipeline runs.

| Script / module | Purpose |
|-----------------|---------|
| [`check_import_surface.py`](check_import_surface.py) | Smoke-test `obsidiandroid` imports and shim parity; orchestrates static ratchets; exits nonzero on failure. |
| [`import_surface_policy.py`](import_surface_policy.py) | AST/file-system only: legacy-root import scans, `# Filename:` header ratchet, legacy-leaf shim rules under `analysis`/`ml_classification`/`model`, UTF-8 BOM scan (shared with tests). |
| [`check_doc_hygiene.py`](check_doc_hygiene.py) | Block known-removed phantom script paths in operator docs; **`make doc-check`**. |
| [`clean_bytecode_cache.py`](clean_bytecode_cache.py) | Remove `__pycache__`, local logs, and common junk under a tree including `.pytest_cache`, `.pytest_tmp*`, `.mypy_cache`, `.ruff_cache`, `htmlcov`, and coverage files (**canonical**; use `python scripts/dev/clean_bytecode_cache.py` or `make clean-bytecode`). |
| [`data_fuzzer.py`](data_fuzzer.py) | Synthetic classification data for stress tests (`sklearn` + pandas). |
| [`run_ml_static_scan.py`](run_ml_static_scan.py) | Argparse driver for the ML predict misuse scan (`python -m scripts.dev.run_ml_static_scan` or `make ml-scan`). |
| [`scan_ml_predict_misuse.py`](scan_ml_predict_misuse.py) | Core walker used by `run_ml_static_scan`. |

### Shell entrypoints (Fedora venv, pytest)

| Script | Purpose |
|--------|---------|
| [`bootstrap_venv.sh`](bootstrap_venv.sh) | Create/refresh `.venv` and install `requirements.txt`; repo-root [`../../setup.sh`](../../setup.sh) delegates here. |
| [`launch_startup_menu.sh`](launch_startup_menu.sh) | Prepend `src/` to `PYTHONPATH` and run `python -m obsidiandroid.cli.startup_menu`; repo-root [`../../run.sh`](../../run.sh) delegates here. |
| [`run_tests.sh`](run_tests.sh) | Fast pytest (`-m "not slow"`); **`make test`** invokes this path. |
| [`run_tests_full.sh`](run_tests_full.sh) | Full pytest including `slow` modules; **`make test-full`** invokes this path. |

**`make test`** and **`make test-full`** invoke these scripts directly (no repo-root wrappers).

**Layout review:** **`make tree-obsidiandroid`** (canonical package tree), **`make tree-source`** (repo root); **`tree-utils`** / **`tree-exporting-shims`** are stubs (former **`utils/`** removed). Requires the **`tree`** utility (`dnf install tree` on Fedora) for **`tree-obsidiandroid`** / **`tree-source`**.

Related **Makefile** shortcuts: **`make setup`** (→ **`./setup.sh`** / **`bootstrap_venv.sh`**), **`make menu`** (→ **`./run.sh`** / **`launch_startup_menu.sh`**), **`make install-editable`** (`pip install -e .`), **`make verify`** (this script + **`make test`**), **`make doc-check`**, **`make ci`** (same as **GitHub Actions**: **`doc-check`** + **`verify`** + **`ml-scan-strict`**).

From the repository root (after `pip install -e .` or `export PYTHONPATH="$PWD/src:$PYTHONPATH"`):

```bash
python scripts/dev/check_import_surface.py
make dev-import-check
```

See also [`docs/STRUCTURE_MIGRATION_PLAN.md`](../../docs/STRUCTURE_MIGRATION_PLAN.md) and [`docs/AGENTS.md`](../../docs/AGENTS.md).
