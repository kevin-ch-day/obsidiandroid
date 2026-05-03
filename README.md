# ObsidianDroid: Android Malware Family Classification Framework

**ObsidianDroid** is a research-focused, open source framework for Android malware analysis and classification. It aggregates VirusTotal vendor results, computes engine weights, builds feature vectors, and trains machine learning classifiers using a reproducible pipeline. ObsidianDroid is designed to be extensible, transparent, and straightforward for researchers and engineers seeking to analyze Android threats at scale.

---

## Features

- **Aggregated AV Vendor Labeling:** Harmonizes VirusTotal vendor results for each sample, normalizing label formats and computing consensus.
- **Engine Weighting:** Quantifies the reliability of each AV engine based on historical detection performance and specificity.
- **Feature Engineering:** Builds permission-based and AV-derived feature vectors for ML, including risk scores, detection density, and consensus ratios.
- **End-to-End ML Pipeline:** Trains and evaluates classifiers (Random Forest, SVM, XGBoost, Logistic Regression) with configurable hyperparameters and grid search support.
- **Output Transparency:** Produces detailed evaluation reports, summary tables, and intermediate feature matrices in the `output/` directory.
- **Extensible/Modular:** Easy to adapt, extend, or integrate with other analysis tools and datasets.
- **Data Inspection & Reporting:** Includes Jupyter notebooks, synthetic data fuzzing tools, and reporting utilities for model diagnostics and auditing.
- **Static Analysis Utilities:** Tools to check for `.predict()` misuse, clean bytecode/log artifacts, and stress-test trainers with synthetic data.

---

## Pipeline Overview

The core workflow (`main.py` → `analysis/pipeline/runner.py`) executes these key steps:

1. **Load Sample Metadata** from a configured MySQL database. Connection defaults and environment overrides are defined in `database/db_config.py` (primary Erebus DB plus the Permission Intel DB; see [Configuration](#configuration) below).
2. **Run AV Engine Analysis** via `analysis/` parsers to collect and normalize vendor labels.
3. **Extract Vendor Metadata** and generate summary statistics/evaluation metrics.
4. **Compute Engine Weights** using specificity, noise, and historical performance (see `analysis/feature_engineering/compute_vendor_scores.py`).
5. **Feature Engineering:** Construct feature vectors from permissions, vendor scores, and consensus features.
6. **Align Features and Labels** for model training; export diagnostics for reproducibility.
7. **Train and Evaluate Models:** Supports Random Forest, SVM, XGBoost, Logistic Regression, with grid search and custom train/test splits.
8. **Summarize Results and Export Labels:** Generate classification predictions, model comparison summaries, and final label tables.

All artifacts (models, reports, diagnostics) are saved under `output/`.

---

## Project Structure

```
ObsidianDroid/
├── analysis/               # AV parsing and feature engineering
├── config/                 # YAML and JSON configs, app and model hyperparameters
├── database/               # DB access helpers and queries
├── data_inspect/           # Jupyter notebooks, analysis scripts, reporting tools
├── ml_classification/      # Model training, validation, and comparison
├── utils/                  # Reusable utilities and exporters
├── testing/                # Synthetic data fuzzers, static scan helpers
├── main.py                 # CLI entry (orchestration in `analysis/pipeline/runner.py`)
├── setup.sh                # Fedora virtual environment setup
├── run.sh                  # Fedora startup menu launcher
├── run_ml_static_scan.py   # Checks for accidental .predict() misuse in code
├── clean_bytecode_cache.py # Utility to remove __pycache__, logs, and artifacts
└── README.md
```

---

## Documentation

- **Documentation hub:** See [`doc/README.md`](doc/README.md) for a curated map of contributor, operator, and user guides.
- **System architecture:** [`doc/architecture.md`](doc/architecture.md) explains end-to-end data flow and package responsibilities.
- **Data sources:** [`doc/data_sources.md`](doc/data_sources.md) describes the replicated VirusTotal tables ObsidianDroid relies on and how to keep them synchronized.
- **Modeling reference:** [`doc/modeling_reference.md`](doc/modeling_reference.md) summarizes supported classifiers, feature families, and evaluation artefacts.
- **User journey:** [`doc/user_guide.md`](doc/user_guide.md) walks analysts through configuration, execution, and troubleshooting.

Each markdown file can be browsed directly in GitHub’s file viewer for quick navigation.

---

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/kevin-ch-day/obsidiandroid.git
   cd obsidiandroid
   ```
2. **Set up the Fedora Python environment:**
   ```bash
   ./setup.sh
   ```
   The setup script creates `.venv`, upgrades `pip`, and installs `requirements.txt`.
3. **(Optional for full pipeline runs) Configure MariaDB/MySQL** by setting `OBSIDIAN_DB_*` and `OBSIDIAN_PERMISSION_INTEL_DB_NAME` (see [Configuration](#configuration)) or by editing the defaults in `database/db_config.py` for local development only. Do not commit real passwords; prefer environment variables or a secrets manager.
   The CLI can launch before database access is fully configured, but database-backed menu actions and pipeline stages still require a working database.
4. **(Optional) Edit pipeline settings** in `config/app_config.py` (model selection, hyperparameters, etc).

---

## Usage

- **Run the Fedora startup menu:**
  ```bash
  ./run.sh
  ```
- Menu options include:
  - Full pipeline
  - Single-model pipeline run (for focused validation)
  - Fast dev pipeline (`dev_fast`)
  - Smoke pipeline (`dev_smoke`) for quickest sanity checks
  - Run pipeline to a selected cutoff stage
  - Additional cutoff targets: ablation, permission trends, and label resolution
  - Vendor parsing only (stop before ML)
  - Engine scoring summary from DB
  - Parser coverage validation from latest AV export
  - Single-vendor parser diagnostics from latest AV export
- **Manual run (after Fedora venv activation):**
  ```bash
  source .venv/bin/activate
  python -m utils.startup_menu
  ```
  The pipeline is profile-driven (`profiles/*.yaml`) and requires explicit profile selection.
  Use `dev_fast` for rapid local iteration (single model, CV/ablation/reporting off).
  Use `dev_smoke` for shortest turnaround (small cohort, vendor-only features, minimal exports).
  For direct invocation:
  ```bash
  python -c "import main; raise SystemExit(main.run_pipeline(profile_ref='banker'))"
  ```

- **Outputs:** Results (trained models, evaluation summaries, feature matrices) are saved in `output/`, including:
  - `final_classification_labels.xlsx` – Predicted malware family per sample.
  - `diagnostics/model_comparison_summary_<run_id>.csv` - Ranked model metrics (default fast path).
  - `model_comparison_summary.xlsx` - Optional ranked model workbook export.
  - Feature matrix with AV and permission-based statistics.

---

## Configuration

### Database (split Erebus + Permission Intel)

ObsidianDroid reads **operational sample metadata, VirusTotal aggregates, and catalog fields** from the primary Erebus database (default schema name `erebus_threat_intel_prod`). It reads **live Android permission intelligence** (`android_permission_*` tables) from the Permission Intel database (default `android_permission_intel`). Both schemas normally live on the same MySQL/MariaDB server; queries use the credentials below for both connections.

Override via environment variables (recommended for deployment):

| Variable | Purpose |
| --- | --- |
| `OBSIDIAN_DB_HOST`, `OBSIDIAN_DB_PORT` | Server host and port |
| `OBSIDIAN_DB_USER`, `OBSIDIAN_DB_PASSWORD` | Credentials (same user typically has `SELECT` on both schemas) |
| `OBSIDIAN_DB_NAME` | Primary Erebus schema |
| `OBSIDIAN_PERMISSION_INTEL_DB_NAME` | Permission Intel schema |

Defaults match `database/db_config.py`. Cross-schema SQL (for example joining `malware_sample_catalog` to `android_permission_obs_sample`) fully qualifies both schema names so ObsidianDroid does not rely on live `android_permission_*` tables inside the primary DB.

Quick connectivity check (requires network access to the DB):

```bash
python -m database.split_db_health
```

### Pipeline and model settings

Model and pipeline settings can be customized in `config/settings/*.py` (re-exported by `config/app_config.py`):
- Train/test split, random seed, estimator hyperparameters.
- Enable/disable grid search (e.g., `ENABLE_RF_GRID_SEARCH`).
- Edit vendor selection (top-k by ML score, inclusion/exclusion of generic vendors).
- Tune XGBoost multiclass runtime guardrails (`XGB_GUARDRAIL_PROFILE_CAPS`) to cap boosting rounds and early stopping for large class spaces.
- Disable heavyweight hot-path Excel exports by default with `ENABLE_AV_PIPELINE_EXCEL_EXPORT = False`.
- Reuse AV verdict query results during iterative local runs with:
  - `ENABLE_AV_VERDICT_QUERY_CACHE = True`
  - `AV_VERDICT_QUERY_CACHE_SIZE = 2`
- Enforce trusted-vendor-only feature selection (optional):
  - `FEATURE_ENFORCE_TRUSTED_VENDOR = True`
- Keep model-summary export lightweight by default with:
  - `ENABLE_MODEL_COMPARISON_CSV_EXPORT = True`
  - `ENABLE_MODEL_COMPARISON_EXCEL_EXPORT = False`
- Per-profile runtime toggles are supported via `runtime_overrides` in profile YAML (for example in `profiles/dev_fast.yaml`).
- Vendor parser tuning diagnostics are exported during runs:
  - `output/diagnostics/vendor_parser_stress_test.latest.csv`
  - `output/diagnostics/vendor_parser_strengths_weaknesses.latest.csv`
- Example: Narrow the Random Forest grid search:
  ```python
  RF_PARAM_GRID = {"n_estimators": [100, 200]}
  ENABLE_RF_GRID_SEARCH = False
  ```

See comments in `config/settings/*.py` (or `config/app_config.py`) for full details.

---

## Optional Tools

- `python run_ml_static_scan.py` – Scan the repo for accidental `.predict()` misuse.
- `python clean_bytecode_cache.py [path] --exclude venv` – Remove bytecode/logs.
- `python analysis/evaluation/random_forest_diagnostics.py` – Cross-validation, weak class detection, feature importance diagnostics.
- `python testing/data_fuzzer.py` – Generate large synthetic datasets for robustness and stress testing.

---

## Running Tests

After installing dependencies, run the **default fast suite** (recommended for local loops):

```bash
pytest -q
# or
./run_tests.sh
# or
make test
```

This excludes integration-heavy modules tagged `slow` (see `pytest.ini` and `tests/conftest.py`).

For the **complete** suite (CI / pre-merge):

```bash
./run_tests_full.sh
# or
make test-full
```

---

## Contributing

Contributions are welcome! To propose enhancements, bug fixes, or new features:
- Fork the repository and submit a pull request.
- Please include tests and documentation for new features.
- Open issues for questions, ideas, or feedback.

---

## License

MIT License (see [LICENSE](LICENSE)).  
For academic and research use only. Commercial use requires written permission.  
Handle malware data responsibly and comply with VirusTotal terms and all applicable laws.

---
