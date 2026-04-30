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
       └────────────── database/ ───────────────> testing/ + reports
```

1. **Metadata ingestion** loads sample identifiers, vendor detections, and contextual attributes from a MySQL database using helpers in `database/`. See [`data_sources.md`](data_sources.md) for a catalog of required tables and replication guidance.
2. **Analysis and feature engineering** normalize AV labels, score vendors, and build per-sample feature matrices in `analysis/` with shared helpers in `utils/`.
3. **Model training and inference** leverage estimators defined in `ml_classification/` using configuration from `config/`.
4. **Evaluation and export** routines write canonical family labels, diagnostics, and artifacts under `output/`.

## Pipeline Stages in Detail

### 1. Metadata Ingestion (`database/`)
- `db_config.py` centralizes MySQL credentials and connection pooling.
- `queries.py` and `loader.py` fetch raw detections, permission metadata, and vendor statistics.
- Data access functions emit pandas DataFrames that downstream modules consume.

#### VirusTotal-backed tables
- `vt_av_engines` lists every VirusTotal engine along with trust and activity metadata used during scoring.
- `vt_av_engines_results` stores per-sample detections that feed the binary engine matrix.
- `vt_av_engine_detections` and companion rollups provide historical hit rates for disagreement analysis.
- Sample metadata queries expose VirusTotal-derived hints such as `vt_suggested_label`, `vt_scan_status`, and first submission timestamps.
- All access occurs through internal SQL helpers—no live API calls are issued during pipeline runs, so availability hinges on the replicated VirusTotal tables inside the project database.

### 2. Label Harmonization & Vendor Scoring (`analysis/`)
- `label_normalization/` maps vendor-specific strings to canonical family names and records alias relationships.
- `vendor_scoring.py` estimates per-engine reliability scores based on historical accuracy.
- `feature_engineering/` assembles:
  - Binary permission usage vectors.
  - Vendor consensus ratios and confidence intervals.
  - Aggregated statistics (e.g., detection counts, time-series trends).
- Shared helpers in `analysis/utils.py` orchestrate cleaning, deduplication, and logging.

### 3. Feature Management (`utils/`)
- `matrix_io.py` serializes sparse/dense matrices to disk for reproducibility.
- `config_loader.py` parses YAML/JSON settings and merges environment overrides.
- `logging.py` standardizes structured logging to stdout and files.

### 4. Model Selection & Training (`ml_classification/`)
- `model_factory.py` returns configured estimators (Random Forest, SVM, XGBoost, Logistic Regression, Gradient Boosting).
- `train.py` coordinates cross-validation, hyperparameter sweeps, and persistence of fitted models.
- `evaluation.py` produces metrics such as precision/recall per family, confusion matrices, and feature importances.
- `ensembles/` contains stacking and voting strategies that blend multiple base learners.

Consult [`modeling_reference.md`](modeling_reference.md) for estimator-specific tips, feature group definitions, and evaluation artefact summaries.

### 5. Configuration (`config/`)
- `app_config.py` toggles feature sets, vendor inclusion criteria, and ensemble weights.
- `model_params/` holds estimator-specific hyperparameters.
- `thresholds.json` defines probability or consensus cutoffs used during final family selection.

### 6. Execution Entrypoints (`main.py`, `model_tuning.py`, `scripts/`)
- `main.py` is the orchestration entrypoint and now delegates major stages to dedicated helpers in `analysis/pipeline/stage_*.py`.
- `analysis/pipeline/stage_samples.py` handles cohort load/readiness checks and reproducibility hooks.
- `analysis/pipeline/stage_av_vendor.py` runs AV analysis, vendor metadata extraction, and feature-label alignment validation.
- `analysis/pipeline/stage_feature_enrichment.py` applies optional metadata feature enrichment before vectorization.
- `analysis/pipeline/stage_modeling.py` covers engine-weight calculation, feature matrix construction, model training, and final label resolution.
- `analysis/pipeline/stage_manifest.py` centralizes run-manifest generation and persistence.
- `analysis/pipeline/sample_preparation.py` contains shared filtering/metadata feature helpers used across stages.
- `model_tuning.py` performs targeted hyperparameter searches based on the same configuration files.
- `scripts/` includes CLI utilities for recurring tasks such as refreshing vendor score tables or exporting feature snapshots.
- For extension patterns and compatibility details, see [`pipeline_staging_guide.md`](pipeline_staging_guide.md).

### 7. Quality Assurance (`testing/`)
- `tests/` provides pytest suites that validate feature builders, data loaders, and model wrappers.
- `testing/data_fuzzer.py` generates adversarial datasets to stress test transformations.
- `testing/static_checks/` contains heuristics that guard against training/testing leakage.

## Data Contracts

| Artifact | Producer | Consumer | Notes |
| --- | --- | --- | --- |
| `detections` DataFrame | `database/loader.py` | `analysis/label_normalization/` | Raw vendor strings keyed by sample SHA. |
| `vendor_scores` table | `analysis/vendor_scoring.py` | `analysis/feature_engineering/`, `ml_classification/` | Weighted by historical accuracy. |
| `feature_matrix.npz` | `analysis/feature_engineering/` | `ml_classification/train.py` | Contains permission flags, consensus ratios, and reliability weights. |
| `labels.csv` | `ml_classification/evaluation.py` | Analysts, downstream systems | Final recommended family per sample. |

## Extending the System

1. Add new feature builders under `analysis/feature_engineering/` and register them in `config/app_config.py`.
2. Implement additional estimators in `ml_classification/models/` and expose them through `model_factory.py`.
3. Update `tests/` to cover new logic and run `pytest -q` before submitting changes.
4. Document new behaviour in `doc/user_guide.md` or dedicated markdown files to keep operators informed.

By following this guide, contributors can map requirements to the correct modules and understand how data flows through ObsidianDroid.
