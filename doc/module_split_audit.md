# Module Split Audit

This audit identifies oversized scripts/modules and split targets to reduce maintenance risk.

## Current hotspots (refreshed)

Command used:

```bash
python data_inspect/inspect_complexity_hotspots.py --top-files 15 --top-functions 20
```

Top file hotspots (production + orchestration paths):

- `analysis/pipeline/stage_permission_trends_report.py` (4149 LOC, max function 831 LOC)
- `analysis/pipeline/stage_manifest.py` (2725 LOC, max function 435 LOC)
- `utils/startup_menu.py` (1621 LOC)
- `main.py` (1545 LOC, `run_pipeline` 745 LOC)
- `analysis/pipeline/stage_results_warehouse.py` (1167 LOC)
- `utils/export_manager.py` (851 LOC)
- `ml_classification/training/pipeline_core.py` (650 LOC)
- `ml_classification/labeling/classification_label_resolver.py` (578 LOC)

Largest function hotspots:

- `analysis/pipeline/stage_permission_trends_report.py:91` `run_permission_trends_report_stage` (831 LOC)
- `main.py:761` `run_pipeline` (745 LOC)
- `analysis/pipeline/stage_manifest.py:64` `finalize_run_manifest_stage` (435 LOC)
- `analysis/pipeline/stage_manifest.py:1447` `_build_strict_paper2_exports` (403 LOC)
- `analysis/pipeline/stage_samples.py:52` `load_and_prepare_samples` (248 LOC)
- `ml_classification/labeling/classification_label_resolver.py:234` `_export_taxonomy_consistency_audit` (217 LOC)
- `utils/export_manager.py:492` `write_excel_file` (213 LOC)

## Complexity signals to prioritize

1. **Pipeline stage overload**
   - `stage_permission_trends_report.py` and `stage_manifest.py` combine orchestration, analytics, export, compliance, and persistence concerns in single modules/functions.
2. **Control-flow depth + broad exception handling**
   - `main.py`, `stage_manifest.py`, and `export_manager.py` contain high branch counts and multiple broad `except Exception` handlers.
3. **Operational UI mixed with workflow logic**
   - `utils/startup_menu.py` still contains substantial action logic that should live in dedicated service modules.
4. **Classification label audit complexity growth**
   - `classification_label_resolver.py` now includes increasingly rich taxonomy checks and should be split into extractor, matcher, and report-writer submodules.

## Split priority (recommended order)

1. `analysis/pipeline/stage_permission_trends_report.py`
2. `analysis/pipeline/stage_manifest.py`
3. `main.py`
4. `utils/startup_menu.py`
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

### 3) `main.py` split

Move into:

- `analysis/orchestration/pipeline_runner.py`
- `analysis/orchestration/runtime_context.py`
- `analysis/orchestration/stage_dispatch.py`
- `analysis/orchestration/finalization.py`

Goal: keep `main.py` as a thin CLI entrypoint.

### 4) `utils/startup_menu.py` split

Move into:

- `utils/menu/maintenance.py`
- `utils/menu/structural_analysis.py`
- `utils/menu/model_evaluation.py`
- `utils/menu/run_context.py`

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
python data_inspect/inspect_complexity_hotspots.py --top-files 30 --top-functions 30
python data_inspect/inspect_module_size_hotspots.py --top-files 30 --top-functions 30
```
