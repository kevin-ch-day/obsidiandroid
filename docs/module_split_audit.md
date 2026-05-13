# Module Split Audit

This audit identifies oversized scripts/modules and split targets to reduce maintenance risk.

**Note:** Line counts below were refreshed against the tree on the date of the last audit edit; re-run the inspection scripts below before relying on exact numbers. Root `main.py` is a **compatibility shim** (~60 LOC); real CLI imports live under **`src/obsidiandroid/cli/`**.

**Pipeline stages:** substantive implementations live under **`src/obsidiandroid/pipeline/`** (`obsidiandroid.pipeline.*`). On-disk **`analysis/pipeline/stage_*.py`** (and most sibling stage-related leaves) are **short identity shims**; hotspot scans and refactors should target **`src/...`** paths, not the shim files.

## Current hotspots (refreshed)

Command used:

```bash
python scripts/diagnostics/inspect_complexity_hotspots.py --top-files 15 --top-functions 20
```

Representative file sizes (production + orchestration paths, approximate):

| Module | LOC (approx.) | Notes |
|--------|----------------|-------|
| `src/obsidiandroid/pipeline/stage_permission_trends_report.py` | ~1910 | Largest stage module (orchestrates `permission_trends` subpackage) |
| `src/obsidiandroid/cli/startup_menu.py` | ~1320 | Operator menu (canonical) |
| `src/obsidiandroid/pipeline/stage_manifest.py` | ~610 | Manifest stage; heavy lifting in `obsidiandroid.pipeline.manifest.*` |
| `src/obsidiandroid/pipeline/runner.py` | ~1590 | `run_pipeline` orchestration (`analysis.pipeline.runner` is a shim) |
| `src/obsidiandroid/pipeline/stage_results_warehouse.py` | ~1170 | Results warehouse stage |
| `obsidiandroid.reporting.export_manager` | ~870 | Exports |
| `src/obsidiandroid/modeling/pipeline_core.py` | ~1020 | Training orchestration (canonical; `ml_classification/training/pipeline_core.py` is a shim) |
| `src/obsidiandroid/labeling/classification_label_resolver.py` | ~770 | Label / taxonomy (canonical; `ml_classification/labeling/classification_label_resolver.py` is a shim) |
| `main.py` (repo root) | ~60 | Shim only — not the LOC-heavy CLI |

Largest function hotspots (see inspect scripts for current line numbers):

- `src/obsidiandroid/pipeline/stage_permission_trends_report.py` — `run_permission_trends_report_stage` (very large)
- `src/obsidiandroid/pipeline/runner.py` — `run_pipeline` (primary orchestration; legacy shim exists)
- `src/obsidiandroid/pipeline/stage_manifest.py` — manifest finalization wiring; submodules under `manifest/`
- `src/obsidiandroid/pipeline/stage_samples.py` — `load_and_prepare_samples`

## Complexity signals to prioritize

1. **Pipeline stage overload**
   - `stage_permission_trends_report.py` and `stage_manifest.py` (under **`src/obsidiandroid/pipeline/`**) still combine orchestration, analytics, export, compliance, and persistence concerns across the stage module + subpackages.
2. **Control-flow depth + broad exception handling**
   - `src/obsidiandroid/pipeline/runner.py` (legacy shim exists), `stage_manifest.py`, and `export_manager.py` contain high branch counts and multiple broad `except Exception` handlers.
3. **Operational UI mixed with workflow logic**
   - `src/obsidiandroid/cli/startup_menu.py` still contains substantial action logic that could move to dedicated service modules over time.
4. **Classification label audit complexity growth**
   - `classification_label_resolver.py` (canonical under **`src/obsidiandroid/labeling/`**) includes rich taxonomy checks and could be split into extractor, matcher, and report-writer submodules.

## Split priority (recommended order)

1. `src/obsidiandroid/pipeline/stage_permission_trends_report.py`
2. `src/obsidiandroid/pipeline/stage_manifest.py`
3. `src/obsidiandroid/pipeline/runner.py` (or extract stage dispatch helpers without moving files in one shot)
4. `src/obsidiandroid/cli/startup_menu.py` (behind-menu workflows → services)
5. `obsidiandroid.reporting.export_manager`
6. `src/obsidiandroid/labeling/classification_label_resolver.py`
7. `src/obsidiandroid/pipeline/stage_results_warehouse.py`

## Proposed target module layout

### 1) `src/obsidiandroid/pipeline/stage_permission_trends_report.py` (further decomposition)

Much logic already lives in **`obsidiandroid.pipeline.permission_trends.*`** (`bundle_*`, `stats`, `stats_core`, `sample_permission_data`, figure/diagnostic exports, …). Prefer **new focused modules under that package** (and thin compatibility shims under **`analysis/pipeline/permission_trends/`** only when a stable legacy import path must be preserved).

Goal: keep `run_permission_trends_report_stage` as orchestration + wiring; push new helpers out of the stage module rather than growing a parallel tree.

### 2) `src/obsidiandroid/pipeline/stage_manifest.py` (tighten boundaries)

Manifest composition, writers, paper exports, and compliance checks are already split across **`obsidiandroid.pipeline.manifest.*`**. Next refactors should clarify **assembly vs validation vs writers** inside that subtree—not reintroduce duplicate layout under **`analysis/pipeline/manifest/`** beyond existing shims.

### 3) Orchestration vs CLI

- Repo-root `main.py` should remain a **thin** import surface for tests (`import main`).
- **`src/obsidiandroid/cli/main.py`** — CLI exports and `main()` entry.
- **`src/obsidiandroid/pipeline/runner.py`** — `run_pipeline` and run-scoped helpers (canonical; legacy shim exists).

Goal: avoid growing new logic in root `main.py`; extend `runner` / stages / `obsidiandroid.*` facades instead.

### 4) `src/obsidiandroid/cli/startup_menu.py` split

Move into (conceptually):

- `obsidiandroid.cli.menu` (maintenance, structural analysis, model evaluation, run context — canonical; legacy **`utils/menu/`** removed)

Goal: menu rendering + dispatch only; move workflows to service functions.

### 5) `obsidiandroid.reporting.export_manager` split

Move into:

- `utils/exporting/excel_writer.py`
- `utils/exporting/csv_writer.py`
- `utils/exporting/error_handling.py`

Goal: reduce broad exception-heavy branches in one file.

### 6) `ml_classification/labeling/classification_label_resolver.py` split

Move into:

- `ml_classification/labeling/taxonomy_extractors.py`
- `ml_classification/labeling/taxonomy_audit.py`
- `ml_classification/labeling/taxonomy_exports.py`

Goal: isolate label extraction, mismatch detection, and report export.

## Refactor guardrails

- Keep backward-compatible wrappers for 2 minor versions where public imports are already used.
- Add/keep tests for each extraction step before moving to next.
- For split-only PRs, avoid behavior changes.
- Run:
  - `pytest -q`
  - targeted module tests for files touched.

## Tracking commands

Use:

```bash
python scripts/diagnostics/inspect_complexity_hotspots.py --top-files 30 --top-functions 30
python scripts/diagnostics/inspect_module_size_hotspots.py --top-files 30 --top-functions 30
```
