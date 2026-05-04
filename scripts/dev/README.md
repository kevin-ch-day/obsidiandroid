# Developer tooling (`scripts/dev/`)

Scripts here support **package layout, import hygiene, and local repo maintenance** — not production pipeline runs.

| Script / module | Purpose |
|-----------------|---------|
| [`check_import_surface.py`](check_import_surface.py) | Smoke-test `obsidiandroid` imports and shim parity; exits nonzero on failure. |
| [`check_doc_hygiene.py`](check_doc_hygiene.py) | Block known-removed phantom script paths in operator docs; **`make doc-check`**. |
| [`clean_bytecode_cache.py`](clean_bytecode_cache.py) | Remove `__pycache__`, local logs, and common junk under a tree (canonical implementation; [`../../clean_bytecode_cache.py`](../../clean_bytecode_cache.py) is a thin repo-root entry). |
| [`data_fuzzer.py`](data_fuzzer.py) | Synthetic classification data for stress tests (`sklearn` + pandas). |
| [`run_ml_static_scan.py`](run_ml_static_scan.py) | Argparse driver for the ML predict misuse scan; repo-root [`run_ml_static_scan.py`](../../run_ml_static_scan.py) delegates here. |
| [`scan_ml_predict_misuse.py`](scan_ml_predict_misuse.py) | Core walker used by `run_ml_static_scan`. |

### Shell entrypoints (Fedora venv, pytest)

| Script | Purpose |
|--------|---------|
| [`bootstrap_venv.sh`](bootstrap_venv.sh) | Create/refresh `.venv` and install `requirements.txt`; repo-root [`../../setup.sh`](../../setup.sh) delegates here. |
| [`launch_startup_menu.sh`](launch_startup_menu.sh) | Prepend `src/` to `PYTHONPATH` and run `python -m utils.startup_menu`; repo-root [`../../run.sh`](../../run.sh) delegates here. |
| [`run_tests.sh`](run_tests.sh) | Fast pytest (`-m "not slow"`); repo-root [`../../run_tests.sh`](../../run_tests.sh) delegates here. |
| [`run_tests_full.sh`](run_tests_full.sh) | Full pytest including `slow` modules; repo-root [`../../run_tests_full.sh`](../../run_tests_full.sh) delegates here. |

**`make test`** and **`make test-full`** invoke these shell scripts directly. Repo-root **`run_tests.sh`** / **`run_tests_full.sh`** are optional thin wrappers to the same files.

**Layout review:** **`make tree-obsidiandroid`** (canonical package tree), **`make tree-utils`** (legacy **`utils/`**), **`make tree-exporting-shims`** (thin export shims), **`make tree-source`** (repo root). Requires the **`tree`** utility (`dnf install tree` on Fedora).

Related **Makefile** shortcuts: **`make setup`** (→ **`./setup.sh`** / **`bootstrap_venv.sh`**), **`make menu`** (→ **`./run.sh`** / **`launch_startup_menu.sh`**), **`make install-editable`** (`pip install -e .`), **`make verify`** (this script + **`make test`**), **`make doc-check`**, **`make ci`** (same as **GitHub Actions**: **`doc-check`** + **`verify`** + **`ml-scan-strict`**).

From the repository root (after `pip install -e .` or `export PYTHONPATH="$PWD/src:$PYTHONPATH"`):

```bash
python scripts/dev/check_import_surface.py
make dev-import-check
```

See also [`docs/STRUCTURE_MIGRATION_PLAN.md`](../../docs/STRUCTURE_MIGRATION_PLAN.md) and [`docs/AGENTS.md`](../../docs/AGENTS.md).
