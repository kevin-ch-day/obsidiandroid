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
| `utils/output_paths.py` | **Deferred** — orchestrates output roots, env overrides, tests (`test_output_paths.py`); easy to break | **move_later** / **needs_review** |

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
- **`utils/output_paths.py`:** **move_later** — keep under `utils/` until a dedicated pass with full `test_output_paths.py` coverage and output-contract review.

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

## Next pass suggestions

1. **Re-export policy:** Decide whether long-term tests should import `obsidiandroid.cli.*` only, or whether shims should expose delegate wrappers (noisy). Prefer canonical imports in tests for anything under monkeypatch.
2. **Move `analysis/pipeline`:** Largest consumer of imports; plan re-exports from `obsidiandroid.pipeline` with root/package shims similar to CLI.
3. **`database` naming:** When moving DB access, clarify imports: top-level `database` vs `obsidiandroid.database` to avoid mistaken cross-imports.
4. **Docs:** Update `AGENTS.md` / `README.md` paths (`utils.pipeline_entry` vs `obsidiandroid.cli.pipeline_entry`) when you want new imports to be the documented default.
5. **Editable install:** Confirm `pip install -e .` in CI once network allows; validates `[tool.setuptools.packages.find]` with `where = ["src", "."]`.
