# Module Split Audit

This audit identifies oversized scripts/modules and split targets to reduce maintenance risk.

**Note:** Line counts below were refreshed on 2026-09-19 with
`python scripts/diagnostics/inspect_complexity_hotspots.py --top-files 15 --top-functions 20`.
Root `main.py` is a **compatibility shim** (60 LOC); real CLI imports live under **`src/obsidiandroid/cli/`**.

**Pipeline stages:** substantive implementations live under **`src/obsidiandroid/pipeline/`** (`obsidiandroid.pipeline.*`). Hotspot scans and refactors should target those canonical paths.

## Current hotspots (refreshed)

Command used:

```bash
python scripts/diagnostics/inspect_complexity_hotspots.py --top-files 15 --top-functions 20
```

Representative file sizes (production + orchestration paths, approximate):

| Module | LOC | Notes |
|--------|-----|-------|
| `src/obsidiandroid/pipeline/stage_permission_trends_report.py` | 4271 | Largest production file; `run_permission_trends_report_stage` is 1229 lines |
| `src/obsidiandroid/pipeline/runner.py` | 2075 | `run_pipeline` is 1884 lines with 16 broad `except` handlers |
| `src/obsidiandroid/database/db_sample_metadata_fetchers.py` | 2011 | Cohort / sample metadata SQL |
| `src/obsidiandroid/reporting/research_three_questions.py` | 1727 | Research-question artifact composer |
| `src/obsidiandroid/pipeline/stage_ablation.py` | 1658 | Ablation experiment stage |
| `src/obsidiandroid/database/db_cohort_readiness.py` | 1655 | Readiness snapshot SQL and reporting |
| `src/obsidiandroid/reporting/type_permission_pattern_report.py` | 1578 | Type-level permission pattern report |
| `src/obsidiandroid/reporting/operator_dashboard.py` | 1567 | Operator research dashboard |
| `src/obsidiandroid/modeling/pipeline_core.py` | 1234 | Training orchestration |
| `src/obsidiandroid/pipeline/stage_results_warehouse.py` | 1171 | Results warehouse stage |
| `src/obsidiandroid/pipeline/stage_manifest.py` | 1053 | Manifest stage; heavy lifting in `obsidiandroid.pipeline.manifest.*` |
| `src/obsidiandroid/labeling/classification_label_resolver.py` | 1012 | Label / taxonomy resolver |
| `obsidiandroid.reporting.export_manager` | 964 | Export orchestration |
| `src/obsidiandroid/cli/startup_menu.py` | 890 | Operator menu (canonical) |
| `main.py` (repo root) | 60 | Shim only — not the LOC-heavy CLI |

Largest function hotspots (current line numbers from the inspector):

- `src/obsidiandroid/pipeline/runner.py:192` — `run_pipeline` (1884 lines, 16 broad `except`)
- `src/obsidiandroid/pipeline/stage_permission_trends_report.py:167` — `run_permission_trends_report_stage` (1229 lines)
- `src/obsidiandroid/reporting/research_three_questions.py:474` — `write_research_question_artifacts` (883 lines)
- `src/obsidiandroid/reporting/operator_dashboard.py:818` — `emit_research_operator_report` (750 lines)
- `src/obsidiandroid/pipeline/stage_samples.py:195` — `load_and_prepare_samples` (731 lines)
- `src/obsidiandroid/pipeline/stage_manifest.py:349` — `finalize_run_manifest_stage` (705 lines)

## Complexity signals to prioritize

1. **Pipeline stage overload**
   - `stage_permission_trends_report.py` and `stage_manifest.py` (under **`src/obsidiandroid/pipeline/`**) still combine orchestration, analytics, export, compliance, and persistence concerns across the stage module + subpackages.
2. **Control-flow depth + broad exception handling**
   - `src/obsidiandroid/pipeline/runner.py`, `stage_manifest.py`, and `export_manager.py` contain high branch counts and multiple broad `except Exception` handlers.
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

Much logic already lives in **`obsidiandroid.pipeline.permission_trends.*`** (`bundle_*`, `stats`, `stats_core`, `sample_permission_data`, figure/diagnostic exports, …). Prefer **new focused modules under that package**.

Goal: keep `run_permission_trends_report_stage` as orchestration + wiring; push new helpers out of the stage module rather than growing a parallel tree.

### 2) `src/obsidiandroid/pipeline/stage_manifest.py` (tighten boundaries)

Manifest composition, writers, paper exports, and compliance checks are already split across **`obsidiandroid.pipeline.manifest.*`**. Next refactors should clarify **assembly vs validation vs writers** inside that subtree.

### 3) Orchestration vs CLI

- Repo-root `main.py` should remain a **thin** import surface for tests (`import main`).
- **`src/obsidiandroid/cli/main.py`** — CLI exports and `main()` entry.
- **`src/obsidiandroid/pipeline/runner.py`** — `run_pipeline` and run-scoped helpers.

Goal: avoid growing new logic in root `main.py`; extend `runner` / stages / `obsidiandroid.*` facades instead.

### 4) `src/obsidiandroid/cli/startup_menu.py` split

Move into (conceptually):

- `obsidiandroid.cli.menu` (maintenance, structural analysis, model evaluation, run context — canonical; legacy **`utils/menu/`** removed)

Goal: menu rendering + dispatch only; move workflows to service functions.

### 5) `obsidiandroid.reporting.export_manager` split

Prefer **incremental extractions alongside `export_manager`** (dedicated writer modules under `src/obsidiandroid/reporting/` or a small `reporting/exports/` subtree) rather than a one-shot mega-move. Goal: narrow `try`/`except` branches and isolate CSV/XLSX writers behind small helpers.

### 6) `src/obsidiandroid/labeling/classification_label_resolver.py` split

Move into (conceptually under **`src/obsidiandroid/labeling/`**):

- `taxonomy_extractors.py`
- `taxonomy_audit.py`
- `taxonomy_exports.py`

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
