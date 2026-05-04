# Architecture and Component Reference

This document explains how ObsidianDroid ingests antivirus telemetry, computes reliability metrics, and produces final malware family assignments. It also maps the source tree so contributors can quickly locate the code that implements each stage.

## High-Level Flow

```
┌──────────────┐     ┌────────────────┐     ┌────────────────┐     ┌────────────────┐
│ Sample/AV DB │ --> │ analysis/      │ --> │ ml_classification │ --> │ output/ exports │
└──────────────┘     │ + utils/      │     │ + config/       │     └────────────────┘
       ▲              └────────────────┘     └────────────────┘
       │                     │                        │
       │                     ▼                        │
       │              Feature matrices                 │
       │                                                ▼
       └────────────── database/ ───────────────> devtools/ + reports
```

1. **Metadata ingestion** loads sample identifiers, vendor detections, and contextual attributes from a MySQL database using helpers in `database/`. See [`data_sources.md`](data_sources.md) for a catalog of required tables and replication guidance.
2. **Analysis and feature engineering** normalize AV labels, score vendors, and build per-sample feature matrices in `analysis/` with shared helpers in `utils/`.
3. **Model training and inference** leverage estimators defined in `ml_classification/` using configuration from `config/`.
4. **Evaluation and export** routines write canonical family labels, diagnostics, and artifacts under `output/`.

**Run-scoped path snapshot:** `analysis/pipeline/run_bounds.py` exposes `PipelineRunBounds` (set at the end of profile + evidence-mode path setup in `runner.py`, cleared when the run finishes). New diagnostics helpers can use `get_pipeline_run_bounds()` instead of re-deriving paths from scattered `app_config` keys. **DB settings surface:** `database/settings.py` provides `load_connection_settings()` as a typed view of `database/db_config` for scripts and tooling.

## Pipeline Stages in Detail

### 1. Metadata Ingestion (`database/`)
- `db_config.py` centralizes MySQL credentials (including the split **primary Erebus** schema and **Permission Intel** schema via environment variables; see [`data_sources.md`](data_sources.md)).
- `db_engine.py` runs SQL against the primary DB; `execute_permission_query()` targets Permission Intel for live `android_permission_*` tables.
- `db_sample_metadata_fetchers.py`, `db_sample_metadata_queries.py`, and `db_sample_metadata_contracts.py` load cohorts and enforce query contracts.
- `db_av_engine_verdicts.py` and related modules read VirusTotal-style verdict matrices and vendor metadata.

#### VirusTotal-backed tables (primary schema)
- Typical physical names include `virustotal_vendor_engines`, `virustotal_sample_vendor_engine_verdicts`, `malware_sample_catalog`, and related summaries—see [`data_sources.md`](data_sources.md) for the authoritative list.

### 2. Label Harmonization & Vendor Scoring (`analysis/`)
- `analysis/vendor_processing/` parses vendor-specific strings into normalized tokens and families.
- `analysis/feature_engineering/compute_vendor_scores.py` derives ML-oriented vendor scores and parser gates.
- `feature_engineering/` also builds cohort statistics, pattern metrics, and supporting aggregates used in reporting.

### 3. Shared Utilities (`utils/`)
- `utils/logging/` and `utils/exporting/` handle structured logs and workbook/Excel exports.
- `utils/output_paths.py`, `utils/run_manifest.py`, and `utils/profile_manager.py` manage run IDs, manifests, and profiles.
- `utils/ui/` provides console UI primitives; thin shims like `display_utils.py` keep older import paths working.

### 4. Model Selection & Training (`ml_classification/`)
- `ml_classification/training/model_trainer_factory.py` coordinates train/test splits, optional SMOTE, and trainer dispatch.
- `ml_classification/training/pipeline_core.py` runs the main classifier pipeline (multiple estimators, CV optional).
- `ml_classification/vectorization/feature_vector_builder.py` and related modules assemble numerical feature matrices.
- Trainers live under `ml_classification/training/ml_trainers/`.

Consult [`modeling_reference.md`](modeling_reference.md) for estimator-specific tips, feature group definitions, and evaluation artefact summaries.

### 5. Configuration (`config/`)
- `app_config.py` toggles feature sets, vendor inclusion criteria, and ensemble weights.
- `model_params/` holds estimator-specific hyperparameters.
- `thresholds.json` defines probability or consensus cutoffs used during final family selection.

### 6. Execution Entrypoints (`main.py`, `analysis/pipeline/runner.py`, `scripts/`)
- `main.py` is the **thin CLI entry**: argument parsing and stable symbols for tests (`run_pipeline`, diagnostics paths, and monkeypatch-friendly re-exports).
- `analysis/pipeline/runner.py` holds **`run_pipeline`** orchestration (same stage order as before: samples → AV pipeline → vendor metadata → engine weights → feature matrix → alignment → training → optional ablation → optional permission-trends report → label resolution → manifest).
- `analysis/pipeline/main_facade.py` exposes **`from_main_or()`** so pytest can patch attributes on `main` (for example `finalize_run_manifest_stage`) and have **`runner.run_pipeline`** observe those bindings despite living outside `main.py`.
- `analysis/pipeline/stage_samples.py` loads cohorts and applies gates; `stage_av_vendor.py` runs AV analysis, vendor extraction, and alignment; `stage_modeling.py` covers weights, feature matrix, training, and label resolution.
- `analysis/pipeline/stage_permission_trends_report.py` produces permission analytics (helpers under `analysis/pipeline/permission_trends/`). `stage_manifest.py` writes the run manifest and paper/evidence exports.
- `stage_results_warehouse.py` persists selected outputs when configured.
- Root `model_tuning.py` and `analysis/evaluation/model_tuning.py` are auxiliary tuning entrypoints; `scripts/` holds operational CLIs (warehouse backfill, research utilities).
- For extension patterns, see [`pipeline_staging_guide.md`](pipeline_staging_guide.md) and `main.run_pipeline` / `profiles/*.yaml`.

### 7. Quality Assurance (`tests/`, `devtools/`)
- `tests/` is the primary pytest tree (`pytest -q`); `tests/conftest.py` routes outputs to tmp and guards filesystem writes during tests.
- `devtools/data_fuzzer.py` stresses data transforms; `devtools/scan_ml_predict_misuse.py` is invoked from `run_ml_static_scan.py` for leakage-style static checks.

## Data Contracts

| Artifact | Producer | Consumer | Notes |
| --- | --- | --- | --- |
| Vendor verdict frames | `database/db_av_engine_verdicts.py` | `analysis/pipeline/stage_av_vendor.py` | Wide per-sample vendor matrix for parsers. |
| Sample cohort DataFrames | `database/db_sample_metadata_queries.py` | `analysis/pipeline/stage_samples.py` | Filtered by profile/type slug. |
| Feature matrix | `analysis/pipeline/stage_modeling.py` (`build_feature_matrix_stage`) | `run_feature_alignment_stage`, training | Mix of AV-derived columns and optional permission/metadata features. |
| Run manifest JSON | `analysis/pipeline/stage_manifest.py` | Operators, evidence bundles | Lists artifacts and run provenance. |

## Extending the System

1. Add new feature builders under `analysis/feature_engineering/` (or pipeline stages) and gate them in `config/app_config.py` / profile YAML.
2. Add or wire estimators through `ml_classification/training/model_trainer_factory.py` and `config/settings/model_hyperparams.py`.
3. Extend `tests/` and run `pytest -q` before submitting changes.
4. Document operator-visible behaviour in [`user_guide.md`](user_guide.md) or [`data_sources.md`](data_sources.md) when changing DB contracts or outputs.

## Observability and research-facing audits (`analysis/observability/`)

- **`analysis/observability/`** centralizes structured pipeline narration: taxonomy (`LogCategory`, `LogSeverity`), `PipelineObservabilitySession` (append-only `pipeline_events.jsonl` + `pipeline_stage_summary.csv`), stable helpers in `api.py` (`record_data_population_change`, `record_artifact_write`, etc.), and `finalize_pipeline_observability` which emits `run_observability_summary.json` (authoritative), `pipeline_stage_summary.md`, `partial_failures.md`, and logging audit artifacts.
- **Runner integration:** `analysis/pipeline/runner.py` owns stage timing and wires population/schema transitions into the session; manifest finalization (`analysis/pipeline/stage_manifest.py`) calls finalize so terminal **Run Health** (`run_health.py`) and `run_evidence_index.md` stay aligned with `run_summary.json` / `run_manifest.json`.
- **Research validity & hostile audit:** `analysis/diagnostics/research_validity/bundle.py` orchestrates cohort funnel, claim audit, permission audit, and delegates to `analysis/diagnostics/hostile_audit/`; exported paths feed the manifest and observability rollup.

By following this guide, contributors can map requirements to the correct modules and understand how data flows through ObsidianDroid.
