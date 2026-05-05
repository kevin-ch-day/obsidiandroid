# ObsidianDroid structure migration plan

This document maps the current repository layout to the target `src/obsidiandroid/` domain layout.

## Developer import modes (verified)

Use one of the following so `import obsidiandroid` resolves to `src/obsidiandroid/`:

| Mode | How |
|------|-----|
| **Preferred** | From the repo root: `pip install -e .` (editable install registers the package; plain imports work in any cwd). |
| **Checkout without install** | `export PYTHONPATH="$PWD/src:$PYTHONPATH"` (or your shell equivalent). |
| **`./run.sh`** | Prepends `repo/src` to `PYTHONPATH` before launching Python so the startup menu works without an editable install. |
| **pytest** | `tests/conftest.py` prepends `repo/src` to `sys.path` so tests see `obsidiandroid` even without editable install. |

Quick verification: `python scripts/dev/check_import_surface.py` or `make dev-import-check`.

---

## Status labels

| Status | Meaning |
|--------|---------|
| **moved_now** | Canonical code now lives under `src/obsidiandroid/...` in this pass. |
| **wrapper_kept** | Thin compatibility module at the old import path re-exports or bootstraps the new location. |
| **move_later** | Intended home is known; no move in this pass. |
| **delete_later** | Remove after callers migrate (often paired with a former shim). |
| **needs_review** | Boundary or ownership unclear; decide before moving. |

## Pass 2 (complete): `common.repo_paths` + `pipeline` facade

| Item | Status | Notes |
|------|--------|-------|
| `src/obsidiandroid/common/repo_paths.py` | **moved_now** | Canonical `ensure_repo_src_on_sys_path()` for checkout installs (detects `.../src/obsidiandroid/...`). |
| `utils/repo_import_paths.py` | **wrapper_kept** | Prepends repo `src/` then imports and calls `obsidiandroid.common.repo_paths` (single policy, shims stay tiny). |
| `main.py` (root) | **wrapper_kept** | After local `src/` prepend, calls `ensure_repo_src_on_sys_path()` from `common`. |
| `src/obsidiandroid/common/__init__.py` | **moved_now** | Re-exports `ensure_repo_src_on_sys_path` (starts real `common` content). |
| `src/obsidiandroid/pipeline/__init__.py` | **moved_now** / **wrapper-style** | Re-exports `run_pipeline` from `analysis.pipeline.runner` for **`from obsidiandroid.pipeline import run_pipeline`** (files still under `analysis/pipeline/`). |
| `run.sh` | **moved_now** | Sets `PYTHONPATH="${ROOT_DIR}/src:..."` before invoking Python. |
| `tests/test_obsidiandroid_package_surface.py` | **moved_now** | Verifies pipeline facade identity + idempotent path helper. |

### Pass 2 tests

- **Outcome:** `pytest -q -m "not slow"` — **351 passed** (includes `tests/test_obsidiandroid_package_surface.py`).

## Pass 1 (complete): package shell + CLI

### Target package roots (`src/obsidiandroid/`)

| Path | Status | Notes |
|------|--------|-------|
| `obsidiandroid/__init__.py` | **moved_now** | Package root. |
| `obsidiandroid/cli/` | **moved_now** | `main.py`, `startup_menu.py`, `pipeline_entry.py`, `menu/`, `ui/`. |
| `obsidiandroid/pipeline/` | **move_later** | Placeholder only; code remains in `analysis/pipeline/`. |
| `obsidiandroid/database/` | **move_later** | Placeholder only; avoid confusion with top-level `database/` package. |
| `obsidiandroid/vendors/` | **move_later** | Placeholder. |
| `obsidiandroid/features/` | **move_later** | Placeholder. |
| `obsidiandroid/labeling/` | **move_later** | Placeholder. |
| `obsidiandroid/modeling/` | **move_later** | Placeholder. |
| `obsidiandroid/evaluation/` | **move_later** | Placeholder. |
| `obsidiandroid/diagnostics/` | **move_later** | Placeholder. |
| `obsidiandroid/reporting/` | **move_later** | Placeholder. |
| `obsidiandroid/observability/` | **move_later** | Placeholder. |
| `obsidiandroid/governance/` | **partial** | `evidence_mode_resolver` lives here; compliance/manifest helpers **move_later**. |
| `obsidiandroid/common/` | **partial** | Hashing, canonical CSV/SHA helpers, path safety, runtime diagnostics paths, and checkout ``repo_paths`` live here; see Pass 4. |

### CLI / entrypoint files

| Current path | Target | Status |
|--------------|--------|--------|
| `main.py` | `obsidiandroid/cli/main.py` | **moved_now** (canonical) + **wrapper_kept** at repo root |
| `utils/startup_menu.py` | `obsidiandroid/cli/startup_menu.py` | **moved_now** + **wrapper_kept** |
| `utils/pipeline_entry.py` | `obsidiandroid/cli/pipeline_entry.py` | **moved_now** + **wrapper_kept** |
| `utils/menu/*.py` | `obsidiandroid/cli/menu/*.py` | **moved_now** + **wrapper_kept** under `utils/menu/` |
| `utils/ui/*.py` | `obsidiandroid/cli/ui/*.py` | **moved_now** + **wrapper_kept** under `utils/ui/` |
| `utils/repo_import_paths.py` | *(new)* | **moved_now** | Bootstrap `src/` onto `sys.path` for checkout runs without editable install. |

### Build / tooling

| File | Change | Status |
|------|--------|--------|
| `pyproject.toml` | `[project.scripts] obsidiandroid` → `obsidiandroid.cli.startup_menu:main`; `[tool.setuptools.packages.find] where = ["src", "."]` + `obsidiandroid*` in `include` | **moved_now** |
| `tests/conftest.py` | Prepend `repo/src` to `sys.path` for `import obsidiandroid` during pytest | **moved_now** |

### Intended future moves (not done yet)

| Current area | Target domain | Status |
|--------------|---------------|--------|
| `analysis/pipeline/*` | `obsidiandroid.pipeline` | **move_later** |
| `analysis/vendor_processing/`, `model/vendor`, `model/parsing/`, `ml_classification/engine_weights/` | `obsidiandroid.vendors` | **move_later** |
| `ml_classification/vectorization/` | `obsidiandroid.features` | **move_later** |
| `ml_classification/labeling/` | `obsidiandroid.labeling` | **move_later** |
| `ml_classification/training/` | `obsidiandroid.modeling` | **move_later** |
| `analysis/evaluation/` (and related) | `obsidiandroid.evaluation` | **needs_review** (overlaps with reporting/diagnostics) |
| `analysis/diagnostics/` | `obsidiandroid.diagnostics` | **move_later** |
| `utils/export*`, LaTeX/workbook/paper exporters | `obsidiandroid.reporting` | **move_later** |
| `utils/evidence_mode_resolver` | `obsidiandroid.governance.evidence_mode_resolver` | **moved_now** (shim **wrapper_kept**) |
| compliance, run manifest, cohort readiness, reproducibility | `obsidiandroid.governance` | **move_later** |
| `analysis/observability/`, `utils/logging/` | `obsidiandroid.observability` | **move_later** |
| `utils/hash_utils`, canonicalization, path safety, runtime/output paths | `obsidiandroid.common` | **move_later** |

### Legacy layout to retire after migration

| Item | Status |
|------|--------|
| Root `utils/menu/*.py` shims (star-import) | **delete_later** once imports point at `obsidiandroid.cli.menu` |
| Root `utils/ui/*.py` shims | **delete_later** |
| `utils/repo_import_paths.py` | **delete_later** or fold into `obsidiandroid.common` |
| Root `main.py` shim | **delete_later** (tests rely on `import main`; update tests/docs first) |

## Pass 1 test results

- **Command:** `pytest -q -m "not slow"`
- **Outcome:** 349 passed (155 deselected).
- **Fixes for this pass:** Tests that monkeypatched names on `utils.startup_menu` or `utils.menu.profile_preflight` were updated to patch **`obsidiandroid.cli.startup_menu`** and **`obsidiandroid.cli.menu.profile_preflight`**, because implementation globals live on the canonical modules; thin shims do not intercept runtime name lookup inside functions defined in `obsidiandroid.cli`.
- **Additional:** `tests/test_startup_menu.py` (slow tier) — 24 passed with `-m "slow or not slow"`.

## Pass 3 (complete): `.gitignore`, import smoke script, documentation

| Item | Status | Notes |
|------|--------|-------|
| `.gitignore` | **verified** | Already contained `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.venv/`, `build/`, `dist/`, `*.egg-info/` (no change required for this pass). |
| `scripts/dev/check_import_surface.py` | **moved_now** | Prints resolved paths and checks `run_pipeline` identity; exits nonzero on failure. |
| `make dev-import-check` | **moved_now** | Invokes the smoke script (`Makefile` target). |
| Developer import modes | **moved_now** | Documented in this file, `AGENTS.md`, and `docs/developer_guide.md`. |

## Pass 4 (complete): `obsidiandroid.common` utilities (first batch)

### Modules inspected

| Module | Risk | Decision |
|--------|------|----------|
| `utils/hash_utils.py` | Low — stdlib only | **moved_now** |
| `utils/canonicalization.py` | Low — stdlib only | **moved_now** |
| `utils/path_safety.py` | Low — pathlib only | **moved_now** |
| `utils/runtime_paths.py` | Low — depends on `config.app_config` only | **moved_now** |
| `utils/output_paths.py` | **moved** — canonical :mod:`obsidiandroid.common.output_paths`; **shim** kept at **utils** for legacy ``from utils import output_paths`` | **moved_now** |

### Canonical locations (`src/obsidiandroid/common/`)

| Implementation | Status |
|----------------|--------|
| `hash_utils.py` | **moved_now** |
| `canonicalization.py` | **moved_now** |
| `path_safety.py` | **moved_now** |
| `runtime_paths.py` | **moved_now** |

### Legacy shims (`utils/`)

| Shim | Status |
|------|--------|
| `utils/hash_utils.py` | **wrapper_kept** — `repo_import_paths` + star-import from `obsidiandroid.common.hash_utils` |
| `utils/canonicalization.py` | **wrapper_kept** |
| `utils/path_safety.py` | **wrapper_kept** |
| `utils/runtime_paths.py` | **wrapper_kept** |

### Import updates (canonical-first, minimal blast radius)

- `src/obsidiandroid/cli/menu/vendor_diagnostics.py` now imports `resolve_diagnostics_dir` from **`obsidiandroid.common.runtime_paths`**. Other callers keep **`from utils.runtime_paths`** (same objects via shims).

### Tests

- **New:** `tests/test_obsidiandroid_common_shims.py` — asserts legacy `utils.*` names are identical to `obsidiandroid.common.*` functions/classes.

### Pruning

- **None** — compatibility shims retained; no dead files removed this pass.

### Inspection backlog (no change yet)

- **Duplicate CSV helpers:** `analysis/pipeline/manifest/hashing.py` defines a `canonical_csv_bytes` used by manifest code paths; `utils.canonicalization` / `obsidiandroid.common.canonicalization` defines a different `canonical_csv_bytes(dict rows, fieldnames)` used by training/manifest CSV governance. Same name, different signatures — **needs_review** for future consolidation or renaming.
- **Stale docs:** Many modules still document `from utils.*`; shims remain valid. Prefer new code importing `obsidiandroid.common.*` where practical.
- **`utils/output_paths.py`:** **moved** — implementation in **`obsidiandroid.common.output_paths`** (uses **`repo_root()`** for log layout); pipeline and scripts import the canonical module; **shim** remains.

## Pass 5 (complete): more `obsidiandroid.common` (ML console + distribution printer)

### Modules moved

| Implementation | Notes | Status |
|----------------|-------|--------|
| `obsidiandroid/common/ml_console.py` | Config-driven verbosity gates (`is_minimal`, `is_debug`, …); same deps as before (`config.app_config`). | **moved_now** |
| `obsidiandroid/common/display_distribution.py` | `print_distribution` for pandas `Series`; pandas-only. | **moved_now** |

### Shims (`wrapper_kept`)

| Legacy path | Canonical module |
|-------------|------------------|
| `utils/ml_console.py` | `obsidiandroid.common.ml_console` |
| `utils/display_distribution.py` | `obsidiandroid.common.display_distribution` |

### Canonical import updates

- `src/obsidiandroid/cli/ui/display.py` imports **`obsidiandroid.common.display_distribution`** (CLI UI no longer depends on `utils.display_distribution` for the bundled helper).

### Tooling

- `scripts/dev/check_import_surface.py` also imports **`obsidiandroid.common.hash_utils`**, **`ml_console`**, **`display_distribution`**, and asserts **`utils.hash_utils`** re-exports match the canonical module.

### Tests

- `tests/test_obsidiandroid_common_shims.py` extended with **ml_console** and **display_distribution** identity checks.

### Pruning

- **None** this pass.

## Pass 6 (complete): root layout hygiene (docs + script index; no code moves)

### Scope A — Generated / runtime ignore policy (verified)

All of the following are **ignored** by `.gitignore` (rules in parentheses). When using `git check-ignore -v`, use **directory paths with a trailing slash** for directories (e.g. `obsidiandroid.egg-info/`, `__pycache__/`); bare `obsidiandroid.egg-info` may not match `*.egg-info/`.

| Path / pattern | Rule (see `.gitignore`) |
|------------------|-------------------------|
| `output/` | `output/` |
| `logs/` | `logs/` |
| `.pytest_tmp/` | `.pytest_tmp/` |
| `*.egg-info/` (e.g. `obsidiandroid.egg-info/`) | `*.egg-info/` |
| `__pycache__/` | `__pycache__/` |
| `*.py[cod]` (e.g. `foo.pyc`) | `*.py[cod]` |
| `.venv/` | `.venv/` |
| `build/` | `build/` |
| `dist/` | `dist/` |

**Note:** `git status --ignored` should list these when present (e.g. `!! output/`, `!! logs/`, `!! .venv/`).

### Scope B — Script organization (documentation only)

| Item | Status |
|------|--------|
| `scripts/dev/README.md` | **moved_now** — describes `check_import_surface.py` and `make dev-import-check` |
| `scripts/diagnostics/README.md` | **moved_now** — index of diagnostic scripts (files still at `scripts/*.py`) |
| `scripts/README.md` | **moved_now** — layout table updated for `dev/` and diagnostics index |

### Scope C — Transitional top-level markers

| Path | Status |
|------|--------|
| `README.md` | **moved_now** — “Repository layout (hybrid migration)” + tree lines for `src/`, `scripts/dev/` |
| `data_inspect/README.md` | **moved_now** — short purpose blurb |
| `devtools/README.md` | **moved_now** — short purpose blurb |

**Not moved:** `analysis/`, `database/`, `ml_classification/`, `model/`, `utils/`, `clean_bytecode_cache.py` — still top-level; **core implementation packages are unchanged** this pass.

**Agent policy:** `AGENTS.md` updated with repository layout rules (canonical `src/obsidiandroid/`, transitional top-level packages, thin `utils/` shims, `output/`/`logs/` vs `artifacts/baselines/`, `scripts/dev/` vs diagnostics index, validation commands).

## Pass 7 (complete): `obsidiandroid.governance` — evidence mode

| Item | Status |
|------|--------|
| `src/obsidiandroid/governance/evidence_mode_resolver.py` | **moved_now** — evidence / paper-mode resolution (stdlib + dataclasses only) |
| `utils/evidence_mode_resolver.py` | **wrapper_kept** — `repo_import_paths` + star-import from governance |
| `analysis/pipeline/runner.py` | **moved_now** — imports `from obsidiandroid.governance import evidence_mode_resolver` |
| `tests/test_governance_primitives.py` | **moved_now** — canonical governance import (monkeypatch targets same module as runner) |
| `tests/test_obsidiandroid_governance_shims.py` | **moved_now** — shim vs canonical identity |
| `scripts/dev/check_import_surface.py` | **moved_now** — loads governance module + shim parity check |

**Not changed:** `analysis/pipeline` directory layout; only the import in `runner.py` was repointed. No change to resolution logic.

## Pass 8 (complete): `obsidiandroid.pipeline` facade + script layout cleanup

### Scope A — Pipeline facade

| Symbol | Notes |
|--------|-------|
| `run_pipeline`, `DIAGNOSTICS_DIR`, `PIPELINE_MAIN_LOGGER`, `PARSER_QUALITY_PATH` | **moved_now** — resolved via :func:`__getattr__` from `analysis.pipeline.runner` (stays in sync when tests monkeypatch `runner`); **not** snapshot copies at import time |

**Canonical imports updated:** `obsidiandroid.cli.main`, `obsidiandroid.cli.pipeline_entry` now import from **`obsidiandroid.pipeline`** for those symbols (behavior unchanged).

### Scope B — Scripts / root clutter

| Change | Status |
|--------|--------|
| `scripts/dev/clean_bytecode_cache.py` | **moved_now** — implementation; repo-root **`clean_bytecode_cache.py`** is **wrapper_kept** (delegates to `scripts.dev`) |
| `scripts/dev/data_fuzzer.py`, `scripts/dev/scan_ml_predict_misuse.py` | **moved_now** — canonical copies |
| `devtools/data_fuzzer.py`, `devtools/scan_ml_predict_misuse.py` | **wrapper_kept** — star-import from `scripts.dev` |
| `data_inspect/*.py` (inspect\_*) | **moved_now** → **`scripts/diagnostics/`** |
| `data_inspect/*.py` at repo root | **wrapper_kept** — thin shims → `scripts.diagnostics.*` |
| `run_ml_static_scan.py` | **moved_now** — repo-root shim → **`scripts.dev.run_ml_static_scan`** (which imports `scan_ml_predict_misuse`) |
| `pyproject.toml` `[tool.setuptools.packages.find] include` | **moved_now** — added `devtools*`, `scripts*` |

**Dead files:** none removed without replacement shims.

### Docs / tooling

- `scripts/dev/README.md`, `scripts/diagnostics/README.md`, `data_inspect/README.md`, `devtools/README.md`, root `README.md`, `docs/module_split_audit.md`, `docs/architecture.md`, `docs/data_sources.md` updated for new paths.
- `scripts/dev/check_import_surface.py` validates full pipeline facade vs `runner`.

## Pass 9 (complete): debt / documentation hygiene

| Item | Notes |
|------|--------|
| `pyproject.toml` | Removed **`testing*`** from setuptools `packages.find` — no `testing/` package exists (dead config). |
| `docs/module_split_audit.md` | Refreshed for **src-layout** (shims vs `src/obsidiandroid/cli/`, `runner.py` owns `run_pipeline`, updated LOC guidance). |
| `docs/README.md` | Quick facts: canonical paths, `scripts/dev/` / `scripts/diagnostics/`. |
| `docs/operations_playbook.md` | Storage bullet acknowledges `scripts/diagnostics/` + `data_inspect/` shims. |

## Pass 10 (complete): root layout cleanup

| Item | Notes |
|------|-------|
| `docs/STRUCTURE_MIGRATION_PLAN.md` | **moved_now** — canonical migration doc; repo-root **`STRUCTURE_MIGRATION_PLAN.md`** is **wrapper_kept** (pointer only). |
| `docs/GOVERNANCE.md` | **moved_now** — canonical governance spec; repo-root **`GOVERNANCE.md`** is **wrapper_kept** (pointer only). |
| `config/engine_aliases.yaml` | **moved_now** — engine alias YAML (was repo root); **`analysis/pipeline/engine_normalization.py`** resolves via repo-root path (cwd-independent). |
| `scripts/dev/run_ml_static_scan.py` | **moved_now** — argparse / scan driver; repo-root **`run_ml_static_scan.py`** is **wrapper_kept** (delegates to `scripts.dev.run_ml_static_scan`). |
| `pyproject.toml` | Removed dead **`model_tuning`** from `[tool.setuptools] py-modules` (no matching top-level module). |

## Pass 11 (complete): shell entrypoints under `scripts/dev/`

| Item | Notes |
|------|-------|
| `scripts/dev/bootstrap_venv.sh` | **moved_now** — Fedora venv + `pip install -r requirements.txt`; repo-root **`setup.sh`** is **wrapper_kept**. |
| `scripts/dev/launch_startup_menu.sh` | **moved_now** — `PYTHONPATH=src` + `python -m utils.startup_menu`; repo-root **`run.sh`** is **wrapper_kept**. |
| `scripts/dev/run_tests.sh` | **moved_now** — fast pytest (`-m "not slow"`); repo-root **`run_tests.sh`** is **wrapper_kept** (`make test` unchanged). |
| `scripts/dev/run_tests_full.sh` | **moved_now** — full pytest; repo-root **`run_tests_full.sh`** is **wrapper_kept** (`make test-full` unchanged). |

## Pass 12 (complete): Pass 9 follow-up (diagnostics/devtools shims, docs, Makefile)

### Scope A — Internal imports (canonical `scripts.*`)

| File | Change |
|------|--------|
| `ml_classification/training/pipeline_core.py` | `from scripts.diagnostics import inspect_classification_results as inspector` (replaces `data_inspect`) |
| `analysis/evaluation/vendor_feature_extractor.py` | `from scripts.diagnostics import inspect_vendor_feature_results` |
| `tests/test_data_fuzzer.py` | `from scripts.dev import data_fuzzer` (canonical) |
| `tests/test_devtools_shim.py` | **new** — asserts `devtools.data_fuzzer.generate_fuzz_data` is `scripts.dev.data_fuzzer.generate_fuzz_data` (shim test **removed** in **Pass 24**). |

### Scope B — `data_inspect*` / `devtools*` in `pyproject.toml` *(superseded by **Pass 24**)*

**At Pass 12:** both patterns were **kept** in `[tool.setuptools.packages.find] include` for editable-install compatibility with `from data_inspect …` / `from devtools …`.

**Pass 24:** entries **removed**; **`data_inspect/`** and **`devtools/`** directories **deleted** — use **`scripts.diagnostics`** / **`scripts.dev`** (see **Pass 24** table for off-repo migration).

### Scope C — Stale path comments and docs

- `scripts/diagnostics/inspect_vendor_feature_results.py` and `inspect_parsed_data.py` — first-line **Filename:** comments point at `scripts/diagnostics/...`.
- `tests/README.md` — points operators at **`scripts.dev`** / **`scripts/diagnostics/`** (shim dirs removed in **Pass 24**).

### Scope D — Repo-root wrappers (classification)

| Path | Label | Notes |
|------|--------|-------|
| `clean_bytecode_cache.py` | **keep_root_wrapper** | Thin entry → `scripts.dev.clean_bytecode_cache` |
| `run_ml_static_scan.py` | **keep_root_wrapper** | Thin entry → `scripts.dev.run_ml_static_scan` |
| `run_tests.sh` | **keep_root_wrapper** | Thin entry → `scripts/dev/run_tests.sh` (`make test`) |
| `run_tests_full.sh` | **keep_root_wrapper** | Thin entry → `scripts/dev/run_tests_full.sh` (`make test-full`) |
| `setup.sh` | **keep_root_wrapper** | Thin entry → `scripts/dev/bootstrap_venv.sh` |
| `run.sh` | **keep_root_wrapper** | Thin entry → `scripts/dev/launch_startup_menu.sh` |

### Scope E — Makefile

- **`clean`** is an alias for **`clean-bytecode`**, which invokes **`python scripts/dev/clean_bytecode_cache.py . --exclude venv --exclude .venv`** (same behavior as the former inline recipe).
- **`tree-source`** prints an optional source tree when the **`tree`** utility is installed; otherwise prints a hint and exits 0.

## Pass 13 (complete): fewer top-level doc/config files

| Item | Notes |
|------|-------|
| **`docs/AGENTS.md`** | **moved_now** — full agent/contributor instructions (replaces a long monolithic root **`AGENTS.md`**). |
| **`AGENTS.md` (root)** | **wrapper_kept** — short pointer to **`docs/AGENTS.md`** for tools that expect **`AGENTS.md`** at the repo root. |
| **`pytest.ini`** | **removed** — pytest defaults and **`slow`** marker moved to **`pyproject.toml`** **`[tool.pytest.ini_options]`** (same default selection and **`--basetemp=.pytest_tmp`**). |

## Pass 14 (complete): root wrapper audit + Makefile as operator default

### Makefile now calls canonical dev paths

| Target | Invokes | Notes |
|--------|---------|------|
| **`make test`** | **`./scripts/dev/run_tests.sh`** | Same as repo-root **`run_tests.sh`** (wrapper still available for habit and scripts). |
| **`make test-full`** | **`./scripts/dev/run_tests_full.sh`** | Same as **`run_tests_full.sh`**. |
| **`make ml-scan`** | **`python -m scripts.dev.run_ml_static_scan`** | Same behavior as **`python run_ml_static_scan.py`** (repo-root shim **wrapper_kept** for setuptools / docs). |
| **`make setup`** | **`./setup.sh`** | Wraps **`scripts/dev/bootstrap_venv.sh`**; Fedora-style venv + **`requirements.txt`**. |
| **`make menu`** | **`./run.sh`** | Wraps **`scripts/dev/launch_startup_menu.sh`**; prepends **`src/`** to **`PYTHONPATH`**. |
| **`make install-editable`** | **`python -m pip install -e .`** | Run with venv activated; registers **`obsidiandroid`** for imports outside pytest. |

### Root wrapper classification (deprecation-oriented)

| Path | Label | Rationale |
|------|--------|-----------|
| **`main.py`** | **keep** | CLI entry, monkeypatch surface, setuptools **`py-modules`**. |
| **`run.sh`** | **keep** | Operator muscle memory; prepends **`src/`** for menu runs without editable install. |
| **`setup.sh`** | **keep** | Same; wraps **`scripts/dev/bootstrap_venv.sh`**. |
| **`run_tests.sh`** / **`run_tests_full.sh`** | **wrapper_kept** | Thin **`exec`** to **`scripts/dev/*.sh`**; **Makefile** bypasses them. Safe **delete_later** only after external CI/docs stop referencing `./run_tests.sh` by name. |
| **`clean_bytecode_cache.py`** | **wrapper_kept** | **`make clean`** / **`clean-bytecode`** call **`scripts/dev/clean_bytecode_cache.py`** directly. Root module retained for **`pyproject.toml`** **`py-modules`** and **`python clean_bytecode_cache.py`** docs — **delete_later** only with a packaging/doc migration. |
| **`run_ml_static_scan.py`** | **wrapper_kept** | **`make ml-scan`** uses **`python -m scripts.dev.run_ml_static_scan`**. Root shim **delete_later** only after dropping **`run_ml_static_scan`** from **`py-modules`** and updating all doc examples. |

### Inspecting layout without noise

For reviews, run **`make clean-bytecode`** then **`make tree-source`** (requires **`tree`** on **`PATH`**). **`tree-source`** ignores **`.venv`**, **`output/`**, **`logs/`**, **`.pytest_*`**, **`__pycache__`**, common tool caches, **build/dist**.

### Tests

- After wrapper/layout changes, run **`make verify`** (import smoke + fast pytest).

## Pass 16 (complete): `obsidiandroid.diagnostics` facade (partial)

| Item | Notes |
|------|-------|
| **`src/obsidiandroid/diagnostics/__init__.py`** | Re-exports **`output_inventory`**, **`output_artifact_policy`**, **`feature_lineage_report`** from **`analysis.diagnostics`** (same module objects). |
| **`scripts/dev/check_import_surface.py`** | Verifies facade submodule identity vs **`analysis.diagnostics.*`**. |
| **`tests/test_obsidiandroid_package_surface.py`** | **`test_diagnostics_facade_modules_match_analysis_diagnostics`**. |

Implementation code remains under **`analysis/diagnostics/`**; expand re-exports only after dependency review.

## Pass 17 (complete): PR gate + editor hygiene

| Item | Notes |
|------|-------|
| **`make verify`** | **`check_import_surface.py` + fast pytest** in one command; documented in **README**, **`docs/AGENTS.md`**, **`docs/developer_guide.md`**. |
| **`.editorconfig`** | Root-level: UTF-8, LF, 4-space Python, tab **Makefile**, 2-space YAML. |
| **`.gitattributes`** | `text=auto`; explicit **LF** for **`.py`**, **`.sh`**, **`.md`**, **YAML**. |

## Pass 18 (complete): CI, local parity, optional pre-commit

| Item | Notes |
|------|-------|
| **`.github/workflows/ci.yml`** | **`make verify`** + **`make ml-scan-strict`** on **`push` → `main`** and PRs; Python **3.12**, **`pip install -e .`**. |
| **`.github/dependabot.yml`** | Monthly **GitHub Actions** version bumps. |
| **`.pre-commit-config.yaml`** | Optional: trailing whitespace, EOF, YAML, large-file guard (use with **`pre-commit install`**; not run in CI). |
| **`make ml-scan-strict`** / **`make ci`** | Strict ML scan; **`ci`** = **`doc-check`** + **`verify`** + **`ml-scan-strict`** (older docs omitted **`doc-check`**; workflow includes it). |
| **README** | CI status badge for **`kevin-ch-day/obsidiandroid`**. |

## Pass 19 (complete): CI matrix, pip hygiene, Dependabot pip, Make UX

| Item | Notes |
|------|-------|
| **CI workflow** | **`workflow_dispatch`** (manual runs); **`permissions: contents: read`**; **pip cache** keys on **`requirements.txt`** + **`pyproject.toml`**; **`pip check`** after install; **Python 3.10 and 3.12** matrix (**`fail-fast: false`**). |
| **Dependabot** | **`pip`** ecosystem weekly on repo root **`requirements.txt`** (**`increase-if-necessary`**). |
| **Makefile** | **`.DEFAULT_GOAL := help`** — bare **`make`** prints targets. |
| **`.python-version`** | **`3.12`** — optional hint for **pyenv**/asdf (matches primary CI version). |
| **Root `AGENTS.md`** | One-line pointer to **`make ci`** / **`.github/workflows/ci.yml`**. |

## Pass 20 (complete): consolidated structure audit publication

| Item | Notes |
|------|-------|
| **`docs/ROOT_AND_STRUCTURE_AUDIT.md`** | Deep audit of repo root categories, hybrid-layout rationale, passes timeline, professionalism checklist, prioritized next phases. Linked from **`README.md`** and **`docs/README.md`**. |

## Pass 21 (complete): documentation pruning (phantom paths)

| Item | Notes |
|------|-------|
| **`docs/user_guide.md`** | Removed references to non-existent **`scripts/export_feature_snapshot.py`**, **`scripts/update_vendor_scores.py`**, and **`config/thresholds.json`**; pointed to real pipeline / **`scripts/report_*.py`** / **`make ml-scan`**. |
| **`docs/modeling_reference.md`** | Estimator table aligned with **`ml_classification/training/ml_trainers/`**; removed phantom **`ml_classification/models/`**, **`model_factory.py`**, **`utils/config_loader.py`**, **`analysis/evaluation/report_builder.py`**. |
| **`main.py`** | Dropped redundant **Filename/Purpose** header lines; kept module docstring. |

## Pass 22 (complete): operations / architecture doc alignment

| Item | Notes |
|------|-------|
| **`docs/operations_playbook.md`** | **Data freshness** bullets aligned with **`data_sources.md`** table names; **backfill** points to **`scripts/backfill_permission_trends_warehouse.py`** and states **`backfill_labels.py`** is not shipped. |
| **`docs/architecture.md`** | Removed non-existent **`config/thresholds.json`**; described **app_config** / **profiles** / **labeling** instead. |
| **`docs/code_review.md`** | Banner clarifying document is a **historical review snapshot** vs current **`analysis/pipeline/`** layout. |

## Pass 23 (complete): doc hygiene guardrail

| Item | Notes |
|------|-------|
| **`scripts/dev/check_doc_hygiene.py`** | Fails the build if allowlisted operator docs reintroduce known-removed paths (phantom scripts/modules). |
| **`make doc-check` / `make ci`** | Doc check runs before fast tests; **`.github/workflows/ci.yml`** runs **`make doc-check`** then **`make verify`**. |
| **`tests/test_doc_hygiene.py`** | Subprocess smoke: script exits **0** on the current tree. |

## Pass 24 (complete): remove `data_inspect/` and `devtools/` shims

| Item | Notes |
|------|-------|
| **Audit** | No in-tree production imports of **`data_inspect`** or **`devtools`**; only shims, tests, docs, and **`pyproject.toml`** referred to them. |
| **Deleted** | Entire **`data_inspect/`** and **`devtools/`** trees. |
| **`pyproject.toml`** | Removed **`data_inspect*`** and **`devtools*`** from **`[tool.setuptools.packages.find] include`**. |
| **Tests** | Removed **`tests/test_data_inspect_shim.py`**, **`tests/test_devtools_shim.py`**. |
| **Off-repo migration** | `from data_inspect import M` → `from scripts.diagnostics import M` (or `importlib.import_module("scripts.diagnostics." + name)`). `from devtools import data_fuzzer` → `from scripts.dev import data_fuzzer`. |

*Project briefs may call this work “Pass 14 (shim sunset)”; the migration plan numbers it **Pass 24** to follow **Pass 23**.*

## Pass 25 (complete): first physical moves into `src/obsidiandroid/`

| Item | Notes |
|------|-------|
| **`src/obsidiandroid/common/export_naming.py`** | **Moved** from **`utils/exporting/naming.py`** (workbook / export naming helpers). **`utils/exporting/naming.py`** is a **shim** re-export. |
| **`src/obsidiandroid/cli/prompt_utils.py`** | **Moved** from **`utils/prompt_utils.py`**. **`utils/prompt_utils.py`** is a **shim**; **`obsidiandroid.cli.ui.menu`** imports the **canonical** module. |
| **`src/obsidiandroid/common/export_vendor_raw.py`** | **Moved** from **`utils/exporting/vendor_raw.py`**; shim at **`utils/exporting/vendor_raw.py`**. |
| **`src/obsidiandroid/common/export_workbook.py`** | **Moved** from **`utils/exporting/workbook.py`** (imports **`obsidiandroid.common.export_naming`**); shim at **`utils/exporting/workbook.py`**. |
| **`src/obsidiandroid/reporting/confusion_matrix_exporter.py`** | **Moved** from **`utils/confusion_matrix_exporter.py`**; **`utils/confusion_matrix_exporter.py`** is a **shim**. **`utils/export_manager.py`** imports the **canonical** reporting + common modules. |
| **`src/obsidiandroid/common/output_cleanup_clutter.py`** | Output-wipe glob constants (was **`utils/output_cleanup_clutter.py`**); **`scripts/fresh_pipeline_reset.py`** / **`scripts/cleanup_output_artifacts.py`** import canonical module (**`src/`** prepended at runtime). |
| **`src/obsidiandroid/common/av_detection_tiers.py`** | Tier labels / pandas helpers (unused in-tree but kept for notebooks); **`utils/av_detection_tiers.py`** shim. |
| **`make tree-obsidiandroid`**, **`tree-utils`**, **`tree-exporting-shims`** | Compare **`src/obsidiandroid`** growth vs legacy **`utils/`** (needs **`tree`** on **`PATH`**). |
| **`check_import_surface` / tests** | Parity checks for export helpers, confusion matrix export, cleanup constants, tiers, and **`prompt_yes_no`**. |

More **`utils/`** → **`obsidiandroid.*`** moves can follow the same pattern: implement under **`src/`**, keep a one-line **`utils/`** shim until imports are fully switched.

## Pass 26 (complete): `utils/` reduction — implementation + metrics

This pass is **not** documentation-only: modules were **moved** (canonical under **`src/obsidiandroid/`**, **`utils/`** shims kept), **`sample_metadata_preprocessor`** included after the audit. Dead **`utils/*.py`** pruning had **no new targets** (import-graph scan found **no** orphan top-level modules).

### Metrics (verified on working tree; `find … \| wc -l`)

Heuristic for **shim vs real** (top-level **`utils/*.py`** excluding **`__init__.py`**): **shim** = short compatibility module / delegates to **`obsidiandroid.*`** in the first lines; **real** = substantial implementation still in **`utils/`** (includes **`export_manager`**, **`display_utils`**, **`startup_menu`**, etc.).

| Metric | Before `sample_metadata_preprocessor` move (same tree minus canonical **`sample_metadata_preprocessor`**) | After (current tree) |
|--------|-------------------------------------------------------------------------------------------------------------|----------------------|
| **`utils/*.py` top-level files** | **29** | **29** |
| **`utils/**/*.py` total** | **46** | **46** |
| **Top-level shim-only** (heuristic) | **15** | **16** (**`sample_metadata_preprocessor`** became a shim) |
| **Top-level real implementation** (heuristic) | **13** | **12** |
| **`src/obsidiandroid/**/*.py`** | **44** | **45** (+**`common/sample_metadata_preprocessor.py`**) |
| **Modules moved into `src/obsidiandroid/` this step** | — | **1** (`sample_metadata_preprocessor`) |
| **`utils/*.py` files pruned (deleted)** | — | **0** (import sweep found **no** orphan top-level **`utils`** modules) |

*Interpretation:* **`utils/`** file counts stay flat while migrating because policy keeps **thin shims** at old import paths. Progress shows up as **fewer “real” modules under `utils/`** (by the heuristic above) and **more files under `src/obsidiandroid/`**. Use **`make tree-utils`** vs **`make tree-obsidiandroid`** to compare trees.

### Scope A — `utils/` classification (snapshot)

| Classification | Modules / paths |
|----------------|-----------------|
| **`shim_only`** | **`hash_utils`**, **`canonicalization`**, **`display_distribution`**, **`ml_console`**, **`path_safety`**, **`runtime_paths`**, **`evidence_mode_resolver`**, **`prompt_utils`**, **`confusion_matrix_exporter`**, **`output_cleanup_clutter`**, **`av_detection_tiers`**, **`compliance`**, **`latex_tables`**, **`sample_metadata_preprocessor`**, **`pipeline_entry`**, **`repo_import_paths`**, **`exporting/naming`**, **`exporting/vendor_raw`**, **`exporting/workbook`**, **`menu/*`**, **`ui/*`**. |
| **`dead_candidate`** | *(none newly identified this pass; **`evaluation_summary_printer`**, **`df_inspector`** removed in Pass 25.)* |
| **`common_candidate`** | **`sample_metadata_preprocessor`** ✅ **moved** to **`obsidiandroid.common`** (uses **`obsidiandroid.cli.ui.display`**). |
| **`reporting_candidate`** | **`latex_tables`** ✅ **moved**; **`family_distribution_report`** ✅ **moved** to **`obsidiandroid.reporting.family_distribution_report`** (runner imports canonical; **`utils.family_distribution_report`** shim kept). |
| **`governance_candidate`** | **`compliance`**, **`cohort_readiness_report`**, **`cohort_reproducibility`**, **`run_manifest`**, **`artifacts`** ✅ **moved** under **`obsidiandroid.governance.*`** (shims under **`utils/`**). |
| **`observability_candidate`** | **`logging/`** package — **high_risk_postpone** (pipeline + structured logs). |
| **`cli_candidate`** | **`profile_manager`** ✅ **moved** to **`obsidiandroid.cli.profile_manager`** (**`PROFILES_DIR`** = **`repo_root() / "profiles"`** in **`repo_paths`**); covered by existing **`menu/`**, **`ui/`** shims under **`utils/`**. |
| **`high_risk_postpone`** | **`export_manager.py`** (large / pipeline-facing), **`logging/`**. |
| **`needs_review`** | At Pass 26 snapshot: **`model_exporter.py`**, **`output_hygiene.py`** — both **moved** in **Pass 27** / **Pass 28**. |

### Scope B — Moved this pass

| Canonical | Shim |
|-----------|------|
| **`src/obsidiandroid/governance/compliance.py`** | **`utils/compliance.py`** |
| **`src/obsidiandroid/reporting/latex_tables.py`** | **`utils/latex_tables.py`** |
| **`src/obsidiandroid/common/sample_metadata_preprocessor.py`** | **`utils/sample_metadata_preprocessor.py`** |
| **`src/obsidiandroid/reporting/family_distribution_report.py`** | **`utils/family_distribution_report.py`** |
| **`src/obsidiandroid/cli/profile_manager.py`** | **`utils/profile_manager.py`** |
| **`src/obsidiandroid/governance/cohort_readiness_report.py`** | **`utils/cohort_readiness_report.py`** |
| **`src/obsidiandroid/governance/cohort_reproducibility.py`** | **`utils/cohort_reproducibility.py`** |
| **`src/obsidiandroid/common/output_paths.py`** | **`utils/output_paths.py`** |
| **`src/obsidiandroid/governance/run_manifest.py`** | **`utils/run_manifest.py`** |
| **`src/obsidiandroid/governance/artifacts.py`** | **`utils/artifacts.py`** |

**Internal imports updated:** **`analysis/pipeline/stage_manifest.py`** (`compliance`, **`LatexTableSpec`** / **`render_tabular`**), **`scripts/research/export_publication_tables.py`**, **`tests/test_latex_tables.py`**, **`analysis/pipeline/stage_samples.py`** (`prepare_sample_dataframe` from **`obsidiandroid.common.sample_metadata_preprocessor`**; **`cohort_readiness_report`** / **`cohort_reproducibility`** from **`obsidiandroid.governance.*`**), **`analysis/pipeline/runner.py`** (`family_distribution_report` from **`obsidiandroid.reporting`**; **`profile_manager`** from **`obsidiandroid.cli.profile_manager`**), **`obsidiandroid.cli.main`**, **`obsidiandroid.cli.menu.profile_preflight`**, **`scripts/check_cohort_foundation.py`** (prepend **`src/`** to **`sys.path`**), **`tests/test_profile_manager.py`** (imports canonical module so **`PROFILES_DIR`** monkeypatches apply to **`load_profile`**), **`tests/test_cohort_readiness_report.py`**, **`tests/test_cohort_reproducibility.py`** (canonical governance imports).

**Output paths / hygiene:** **`obsidiandroid.common.output_paths`** and **`obsidiandroid.common.output_hygiene`** are imported across **`analysis/pipeline/`**, **`utils/export_manager`**, **`utils/logging`**, **`ml_classification/`**, **`obsidiandroid.cli`**, **`scripts/`**, and tests (**`test_output_paths`**, **`test_output_hygiene_resolve`**). Legacy **`utils.output_hygiene`** remains a shim.

**Run manifest / artifact manifest:** **`obsidiandroid.governance.run_manifest`** (runner, manifest stages, orchestration, **`tests/test_manifest_pipeline.py`**, **`tests/conftest`** monkeypatch) and **`obsidiandroid.governance.artifacts`** (**`stage_manifest`**, **`paper_compliance_checks`**, **`tests/test_governance_primitives`**).

**Import ergonomics:** **`utils/display_utils.py`** now re-exports **`obsidiandroid.cli.ui.display`** directly (same as **`utils/ui/display.py`**, skipping the extra hop through **`utils.ui`**).

### Scope C — Prune

No additional deletes this pass (prior **`rg`** audit showed no further zero-caller **`utils/`** roots beyond already-pruned files).

### Scope E — Gates

**`check_import_surface`**, **`tests/test_obsidiandroid_package_surface.py`**, fast **`pytest`**, **`doc-check`**.

## Pass 27 (complete): `model_exporter` → `obsidiandroid.modeling`

| Item | Status | Notes |
|------|--------|-------|
| **`src/obsidiandroid/modeling/model_exporter.py`** | **moved_now** | Joblib + JSON export; uses **`obsidiandroid.cli.ui.display`** for console messages and **`config.app_config`** for **`RUNTIME_RUN_ID`**. |
| **`utils/model_exporter.py`** | **wrapper_kept** | Thin shim: **`import *`** from **`obsidiandroid.modeling.model_exporter`** (after **`repo_import_paths`**). |
| **`ml_classification/training/prediction_builder.py`** | **updated** | Imports **`obsidiandroid.modeling.model_exporter`** (canonical). |
| **`tests/test_model_exporter_paths.py`** | **updated** | Canonical import (same **`app_config`** monkeypatch surface). |
| **`scripts/dev/check_import_surface.py`** | **updated** | Parity: **`utils.model_exporter.export_model_to_file`** is **`obsidiandroid.modeling.model_exporter.export_model_to_file`**. |
| **`tests/test_obsidiandroid_package_surface.py`** | **updated** | **`test_model_exporter_shim_matches_canonical`**. |

**Not in this pass:** **`utils/export_manager.py`**, **`utils/output_hygiene.py`**, **`utils/logging/`**, **`analysis/pipeline/`**, broad **`ml_classification/training/`** moves, **`database/`**, **`model/`**.

### Metrics (same heuristic as Pass 26; verified after Pass 27)

| Metric | After Pass 26 | After Pass 27 |
|--------|----------------|---------------|
| **Top-level shim-only** (`utils/*.py`, heuristic) | **16** | **17** (**`model_exporter`** is a shim) |
| **Top-level real implementation** (heuristic) | **12** | **11** |
| **`src/obsidiandroid/**/*.py`** | **52** (tree before this pass) | **53** (+**`modeling/model_exporter.py`**) |

### Scope A — classification delta

- **`shim_only`**: add **`model_exporter`**.
- **`needs_review`**: **`model_exporter`** ✅ **Pass 27**; **`output_hygiene`** ✅ **Pass 28**.

### Scope B — canonical / shim pair

| Canonical | Shim |
|-----------|------|
| **`src/obsidiandroid/modeling/model_exporter.py`** | **`utils/model_exporter.py`** |

## Pass 28 (complete): `output_hygiene` → `obsidiandroid.common`

| Item | Status | Notes |
|------|--------|-------|
| **`src/obsidiandroid/common/output_hygiene.py`** | **moved_now** | Run-scoped vs global **`output/diagnostics`** mirrors; uses **`obsidiandroid.common.output_paths`** and **`config.app_config`**. |
| **`utils/output_hygiene.py`** | **wrapper_kept** | Thin shim: **`import *`** from **`obsidiandroid.common.output_hygiene`**. |
| **`analysis/pipeline/`** (runner, manifest, ablation, sample exports, vendor metadata) | **updated** | **`from obsidiandroid.common import output_hygiene as oh`**. |
| **`analysis/diagnostics/`** (`output_inventory`, feature drop trace) | **updated** | Canonical **`output_hygiene`** imports. |
| **`analysis/orchestration/runtime_reporting.py`** | **updated** | Canonical import. |
| **`obsidiandroid.cli.startup_menu`** | **updated** | Canonical import. |
| **`ml_classification/training/model_trainer_factory.py`** | **updated** | Canonical import. |
| **`tests/test_output_hygiene_resolve.py`** | **updated** | Canonical import. |
| **`scripts/dev/check_import_surface.py`** | **updated** | Parity on **`resolve_stable_output_root_for_mirrors`** and **`mirror_csv_text_run_then_global`**. |
| **`tests/test_obsidiandroid_package_surface.py`** | **updated** | **`test_output_hygiene_shim_matches_canonical`**. |

**Not in this pass:** **`utils/logging/`**, physical **`analysis/pipeline/`** tree move, broad **`ml_classification/training/`**, **`database/`**, **`model/`**. (**`export_manager`** moved in **Pass 29** below.)

### Metrics (heuristic; after Pass 28)

| Metric | After Pass 27 | After Pass 28 |
|--------|----------------|---------------|
| **Top-level shim-only** | **17** | **18** (**`output_hygiene`**) |
| **Top-level real implementation** | **11** | **10** |
| **`src/obsidiandroid/**/*.py`** | **53** | **54** (+**`common/output_hygiene.py`**) |

### Scope B — canonical / shim pair

| Canonical | Shim |
|-----------|------|
| **`src/obsidiandroid/common/output_hygiene.py`** | **`utils/output_hygiene.py`** |

## Consolidation (complete): metadata feature frame

| Item | Notes |
|------|-------|
| **`analysis/pipeline/sample_preparation`** | **Canonical** home for **`build_metadata_feature_frame`** and **`extract_vt_tag_count`** (used by **`stage_feature_enrichment`**). |
| **`analysis/orchestration/metadata_features.py`** | **Thin re-export** of the same functions for backward-compatible imports; **`tests/test_main_metadata_features.py`** imports the canonical module. |

## Dead-code pruning (ongoing)

| Item | Notes |
|------|-------|
| **`ml_classification/vectorization/label_decoder_utils.py`** | **Removed** — **never imported**; label decoding uses **`LabelEncoder`** / builder paths elsewhere. |
| **`ml_classification/training/compare_models.py`** | **Removed** — **never imported**; experimental multi-model compare helper only. |
| **`ml_classification/training/model_runner_helpers.py`** | **Removed** — only imported by **`compare_models.py`** (also removed); production training uses **`train_model_executor`**. |
| **`analysis/evaluation/random_forest_performance_report.py`** | **Removed** — **no** imports/docs; standalone **`__main__`** helper superseded by **`random_forest_diagnostics`** / ML reporting paths. |
| **`analysis/evaluation/vendor_classification_scoring.py`** | **Removed** — **never imported**; workflow duplicated by **`evaluate_av_classifications`** + pipeline scoring stages. |
| **`model/parsing/vendor_parse_result.py`** | **Removed** — **`VendorParseResult`** unused; no references outside the file. |
| **`model/vendor/record_exporter.py`**, **`record_debugger.py`** | **Removed** — **never imported**; debugging/export helpers redundant with **`record_core`** / validators. |
| **`analysis/av_feature_engineering.py`** | **Removed** — **no** imports or doc references; overlapped conceptually with **`analysis/feature_engineering/compute_vendor_scores.py`** (the supported scoring path). |
| **`analysis/orchestration/manifest_finalize.py`** | **Removed** — **never imported**; run manifest finalization lives in **`analysis/pipeline/stage_manifest.py`** (**`finalize_run_manifest_stage`**). |
| **`utils/evaluation_summary_printer.py`** | **Removed** — nothing imported it; evaluation UX lives in **`ml_classification/reporting/`** and exporters. **`docs/modeling_reference.md`** updated. |
| **`utils/df_inspector.py`** | **Removed** — interactive dataframe inspector had **no** in-repo callers. |

## Pass 29 (complete): `export_manager` canonical under `obsidiandroid.reporting`

| Item | Notes |
|------|-------|
| **`src/obsidiandroid/reporting/export_manager.py`** | **moved_now** — Excel/vendor/confusion-matrix export orchestration (formerly **`utils/export_manager.py`** body). Imports **`obsidiandroid.cli.ui.display`**, **`obsidiandroid.common.*`**, **`utils.logging`** (logging move deferred). |
| **`utils/export_manager.py`** | **wrapper_kept** — replaces **`sys.modules['utils.export_manager']`** with the canonical module object so **`from utils import export_manager`** and **`obsidiandroid.reporting.export_manager`** are **identical** (monkeypatch + **`tests/test_export_manager_wiring.py`** stable). |
| **Call sites** | **updated** — **`pipeline_core`**, **`score_av_engines`**, **`evaluate_av_classifications`**, **`vendor_feature_extractor`**, **`classification_label_resolver`**, **`ml_eval_engine`** use **`from obsidiandroid.reporting import export_manager`**. |
| **`scripts/dev/check_import_surface.py`** | **updated** — asserts module identity + **`export_dataframe_to_excel`** binding. |
| **`obsidiandroid.reporting` package** | **updated** — re-exports **`export_manager`** submodule in **`__all__`**. |

**Deferred:** splitting **`export_manager`** into smaller modules; **`utils/logging/`** migration (**Pass 30+** / observability).

## Next pass suggestions

1. **`utils/logging/`** + **`analysis/observability/`** → **`obsidiandroid.observability`** (separate pass; keep **`utils.logging`** shim).
2. **Re-export policy:** Decide whether long-term tests should import `obsidiandroid.cli.*` only, or whether **`utils/`** shims should keep exposing delegate wrappers. Prefer canonical imports in tests for anything under monkeypatch.
3. **Move `analysis/pipeline`:** Largest consumer of imports; plan re-exports from `obsidiandroid.pipeline` with root/package shims similar to CLI.
4. **`database` naming:** When moving DB access, clarify imports: top-level `database` vs `obsidiandroid.database` to avoid mistaken cross-imports.
5. **Docs:** Update `AGENTS.md` / `README.md` paths (`utils.pipeline_entry` vs `obsidiandroid.cli.pipeline_entry`) when you want new imports to be the documented default.
6. **Editable install:** Confirm `pip install -e .` in CI once network allows; validates `[tool.setuptools.packages.find]` with `where = ["src", "."]`.
