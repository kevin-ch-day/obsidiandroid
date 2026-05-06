# Module Split Audit

This audit identifies oversized scripts/modules and split targets to reduce maintenance risk.

**Note:** Line counts below were refreshed against the tree on the date of the last audit edit; re-run the inspection scripts below before relying on exact numbers. Root `main.py` is a **compatibility shim** (~60 LOC); real CLI imports live under **`src/obsidiandroid/cli/`**. **`utils/startup_menu.py`** is a shim; the interactive menu is **`src/obsidiandroid/cli/startup_menu.py`**.

## Current hotspots (refreshed)

Command used:

```bash
python scripts/diagnostics/inspect_complexity_hotspots.py --top-files 15 --top-functions 20
```

Representative file sizes (production + orchestration paths, approximate):

| Module | LOC (approx.) | Notes |
|--------|----------------|-------|
| `analysis/pipeline/stage_permission_trends_report.py` | ~3170 | Largest stage module |
| `src/obsidiandroid/cli/startup_menu.py` | ~2000 | Operator menu (canonical); root `utils/startup_menu.py` is a shim |
| `analysis/pipeline/stage_manifest.py` | ~2570 | Manifest / exports |
| `analysis/pipeline/runner.py` | ~1640 | `run_pipeline` orchestration |
| `analysis/pipeline/stage_results_warehouse.py` | ~1170 | Results warehouse |
| `utils/export_manager.py` | ~860 | Exports |
| `ml_classification/training/pipeline_core.py` | ~900 | Training orchestration |
| `ml_classification/labeling/classification_label_resolver.py` | ~750 | Label / taxonomy |
| `main.py` (repo root) | ~60 | Shim only — not the LOC-heavy CLI |

Largest function hotspots (see inspect scripts for current line numbers):

- `analysis/pipeline/stage_permission_trends_report.py` — `run_permission_trends_report_stage` (very large)
- `analysis/pipeline/runner.py` — `run_pipeline` (primary orchestration)
- `analysis/pipeline/stage_manifest.py` — manifest finalization and paper export helpers
- `analysis/pipeline/stage_samples.py` — `load_and_prepare_samples`

## Complexity signals to prioritize

1. **Pipeline stage overload**
   - `stage_permission_trends_report.py` and `stage_manifest.py` combine orchestration, analytics, export, compliance, and persistence concerns in single modules/functions.
2. **Control-flow depth + broad exception handling**
   - `analysis/pipeline/runner.py`, `stage_manifest.py`, and `export_manager.py` contain high branch counts and multiple broad `except Exception` handlers.
3. **Operational UI mixed with workflow logic**
   - `src/obsidiandroid/cli/startup_menu.py` still contains substantial action logic that could move to dedicated service modules over time.
4. **Classification label audit complexity growth**
   - `classification_label_resolver.py` includes rich taxonomy checks and could be split into extractor, matcher, and report-writer submodules.

## Split priority (recommended order)

1. `analysis/pipeline/stage_permission_trends_report.py`
2. `analysis/pipeline/stage_manifest.py`
3. `analysis/pipeline/runner.py` (or extract stage dispatch helpers without moving files in one shot)
4. `src/obsidiandroid/cli/startup_menu.py` (behind-menu workflows → services)
5. `utils/export_manager.py`
6. `ml_classification/labeling/classification_label_resolver.py`
7. `analysis/pipeline/stage_results_warehouse.py`

## Proposed target module layout

### 1) `analysis/pipeline/stage_permission_trends_report.py` split

Move into:

- `analysis/pipeline/permission_trends/data_prep.py`
- `analysis/pipeline/permission_trends/metrics.py`
- `analysis/pipeline/permission_trends/figures.py`
- `analysis/pipeline/permission_trends/bundle_export.py`
- `analysis/pipeline/permission_trends/warehouse_export.py`

Goal: keep stage entrypoint under ~180 LOC with clear step orchestration.

### 2) `analysis/pipeline/stage_manifest.py` split

Move into:

- `analysis/pipeline/manifest/assembly.py`
- `analysis/pipeline/manifest/compliance_checks.py`
- `analysis/pipeline/manifest/paper_exports.py`
- `analysis/pipeline/manifest/writer_orchestration.py`

Goal: isolate manifest composition vs validation vs writing.

### 3) Orchestration vs CLI

- Repo-root `main.py` should remain a **thin** import surface for tests (`import main`).
- **`src/obsidiandroid/cli/main.py`** — CLI exports and `main()` entry.
- **`analysis/pipeline/runner.py`** — `run_pipeline` and run-scoped helpers.

Goal: avoid growing new logic in root `main.py`; extend `runner` / stages / `obsidiandroid.*` facades instead.

### 4) `src/obsidiandroid/cli/startup_menu.py` split

Move into (conceptually):

- `obsidiandroid.cli.menu` (maintenance, structural analysis, model evaluation, run context — canonical; legacy **`utils/menu/`** removed)

Goal: menu rendering + dispatch only; move workflows to service functions.

### 5) `utils/export_manager.py` split

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
