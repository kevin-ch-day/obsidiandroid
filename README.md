# ObsidianDroid: Android Malware Family Classification Framework

[![CI](https://github.com/kevin-ch-day/obsidiandroid/actions/workflows/ci.yml/badge.svg)](https://github.com/kevin-ch-day/obsidiandroid/actions/workflows/ci.yml)

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
- **Read-only Data Explorer:** The startup menu can browse current catalog summaries and open an explicitly selected retained research packet. Missing permission coverage is shown as unavailable; this route does not train models or request provider data.
- **Static Analysis Utilities:** Tools to check for `.predict()` misuse, clean bytecode/log artifacts, and stress-test trainers with synthetic data.

---

## Pipeline Overview

The core workflow (`main.py` → `obsidiandroid.pipeline.runner`) executes these key steps:

1. **Load Sample Metadata** from a configured MySQL database. Connection defaults and environment overrides are defined in **`obsidiandroid.database.db_config`** for the primary Erebus DB plus the Permission Intel DB; see [Configuration](#configuration) below.
2. **Run AV Engine Analysis** via canonical vendor parsing/execution modules (**`obsidiandroid.vendors`**).
3. **Extract Vendor Metadata** and generate summary statistics/evaluation metrics.
4. **Compute Engine Weights** using specificity, noise, and historical performance (see `obsidiandroid/feature_engineering/compute_vendor_scores.py`).
5. **Feature Engineering:** Construct feature vectors from permissions, vendor scores, and consensus features.
6. **Align Features and Labels** for model training; export diagnostics for reproducibility.
7. **Train and Evaluate Models:** Supports Random Forest, SVM, XGBoost, Logistic Regression, with grid search and custom train/test splits.
8. **Summarize Results and Export Labels:** Generate classification predictions, model comparison summaries, and final label tables.

All artifacts (models, reports, diagnostics) are saved under `output/`.

---

## Retained descriptive research

The existing atlas family and structure views can display an optional, hash-bound
source-context overlay. Catalog URLs, ingestion labels and inferred components
remain distinct from independently supported acquisition origins. Association
contrasts expose exact common-support membership, pooled effects on that same
population, and the separate five-per-cell sensitivity population. Temporal views
include observed-year gaps and retained-report timing.

`python -m obsidiandroid.reporting.integrated_research --packet PATH structure`
uses retained evidence only. A bounded local export needs exact identity, source
and version validation, not a signing service, approval store or arbitrary expiry.
Existing database access restrictions and the separate historical V2 export
contract remain intact. See [offline research](docs/integrated_research.md).

## Version

Current application version: **v2.4.0**.

Release notes: [`docs/RELEASE_NOTES.md`](docs/RELEASE_NOTES.md).
Code-complete checklist: [`docs/releases/2.4.0_CODE_COMPLETE_CHECKLIST.md`](docs/releases/2.4.0_CODE_COMPLETE_CHECKLIST.md).
Offline graph index: [`docs/releases/2.4.0_OFFLINE_GRAPH_INDEX.md`](docs/releases/2.4.0_OFFLINE_GRAPH_INDEX.md).

---

## Repository layout (hybrid migration)

The installable package lives under **`src/obsidiandroid/`** (CLI, `common`, **`obsidiandroid.database`**, `pipeline`, `modeling`, `features`, `labeling`, …). The old repo-root **`analysis/`**, **`ml_classification/`**, **`model/`**, and **`utils/`** Python trees have been retired. Top-level **`database/`** holds versioned SQL assets; use the curated **`obsidiandroid.database`** façade for Python. Details, backlog, and pass history: [`docs/STRUCTURE_MIGRATION_PLAN.md`](docs/STRUCTURE_MIGRATION_PLAN.md).

**Generated / runtime artifacts** (`output/`, `logs/`, virtualenvs, caches, build outputs) are listed in **`.gitignore`** and should not be committed. For a **source-only** tree view after local runs, run **`make clean-bytecode`** then **`make tree-source`** (ignores `output/`, `logs/`, `.venv`, pytest/coverage caches, etc.; install the `tree` utility if needed). Developer import modes (`pip install -e .`, `PYTHONPATH`, pytest): see [`docs/AGENTS.md`](docs/AGENTS.md) (repo-root [`AGENTS.md`](AGENTS.md) is a short pointer).

---

## Project Structure

```
ObsidianDroid/
├── config/                 # YAML and JSON configs, app and model hyperparameters
├── database/               # Versioned SQL assets and migrations
├── docs/                   # Guides (incl. AGENTS, GOVERNANCE, STRUCTURE plan)
├── pyproject.toml          # Packaging, dependencies, pytest defaults
├── main.py                 # CLI entry (implementation in `obsidiandroid.pipeline.runner`)
├── setup.sh                # Wrapper → scripts/dev/bootstrap_venv.sh
├── run.sh                  # Wrapper → scripts/dev/launch_startup_menu.sh
├── src/obsidiandroid/      # Canonical Python package (CLI, common, pipeline facade, …)
├── scripts/dev/            # Dev tools: run_tests.sh, import_surface check, ML scan, bytecode clean, …
├── scripts/diagnostics/   # Data inspection CLIs (see scripts/diagnostics/README.md)
└── README.md
```

---

## Documentation

- **Documentation hub:** See [`docs/README.md`](docs/README.md) for a curated map of contributor, operator, and user guides.
- **Contributor / agent guide:** [`docs/AGENTS.md`](docs/AGENTS.md) (repo-root [`AGENTS.md`](AGENTS.md) links here).
- **Governance:** [`docs/GOVERNANCE.md`](docs/GOVERNANCE.md) describes mandatory runtime and reproducibility policies.
- **canonical closure scope:** [`docs/CANONICAL_RUN_CONTRACTS.md`](docs/CANONICAL_RUN_CONTRACTS.md) records the canonical boundary for permission patterns, DB ownership, inference-vs-rebuild concepts, and what moves to later release.
- **System architecture:** [`docs/architecture.md`](docs/architecture.md) explains end-to-end data flow and package responsibilities.
- **Pipeline staging:** [`docs/pipeline_staging_guide.md`](docs/pipeline_staging_guide.md) maps `runner.py` stages and extension points.
- **Data sources:** [`docs/data_sources.md`](docs/data_sources.md) describes the replicated VirusTotal tables ObsidianDroid relies on and how to keep them synchronized.
- **Modeling reference:** [`docs/modeling_reference.md`](docs/modeling_reference.md) summarizes supported classifiers, feature families, and evaluation artefacts.
- **User journey:** [`docs/user_guide.md`](docs/user_guide.md) walks analysts through configuration, execution, and troubleshooting.

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
3. **Install in editable mode (recommended):**
   ```bash
   source .venv/bin/activate
   pip install -e .
   ```
4. **(Optional for full pipeline runs) Configure MariaDB** by setting explicit
   `OBSIDIAN_DB_*` and Permission Intel connection variables (see
   [Configuration](#configuration)). Source connections no longer fall back to
   root credentials or an embedded password. Do not commit real passwords;
   prefer a private `0600` client option file. Normal profile execution
   defaults to read-only upstream access and no legacy warehouse export;
   explicit native analysis persistence has a separate Core plan and writer.
   See [`docs/runtime_source_connection_policy.md`](docs/runtime_source_connection_policy.md).
   The CLI can launch before database access is fully configured, but database-backed menu actions and pipeline stages still require a working database.
5. **(Optional) Edit pipeline settings** in `config/app_config.py` (model selection, hyperparameters, etc).

### Canonical package & imports (restructure)

After **`pip install -e .`**, new code and tooling should import the **`obsidiandroid`** package (implementation under **`src/obsidiandroid/`**):

```python
from obsidiandroid.pipeline import run_pipeline
from obsidiandroid.database import db_config  # canonical package; repo-root database/ contains SQL only
```

- **Console entrypoint:** `python -m obsidiandroid.cli.startup_menu` (same as the `obsidiandroid` setuptools script after install).
- **Operator / checkout paths:** repo-root **`main.py`** and **`./run.sh`** remain supported; they ensure `src/` is on **`sys.path`** then call into **`obsidiandroid`**. **`import main; main.run_pipeline(...)`** is still valid for quick one-liners.
- **Python import surfaces:** use **`obsidiandroid.*`**. The old repo-root **`analysis/`** and **`ml_classification/`** trees are retired; root **`database/`** is SQL-only. Pass history and remaining moves: [`docs/STRUCTURE_MIGRATION_PLAN.md`](docs/STRUCTURE_MIGRATION_PLAN.md).

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
  python -m obsidiandroid.cli.startup_menu
  ```
  The pipeline is profile-driven (`profiles/*.yaml`) and requires explicit profile selection.
  Use `dev_fast` for rapid local iteration (single model, CV/ablation/reporting off).
  Use `dev_smoke` for shortest turnaround (small cohort, vendor-only features, minimal exports).
  For direct invocation:
  ```bash
  python -c "import main; raise SystemExit(main.run_pipeline(profile_ref='banker'))"
  ```

- **Quick dev checks (mirrors CI):**
  ```bash
  make ci
  ```

- **Outputs:** Results (trained models, evaluation summaries, feature matrices) are saved in `output/`, including:
  - `final_classification_labels.xlsx` – Predicted malware family per sample.
  - `diagnostics/model_comparison_summary_<run_id>.csv` - Ranked model metrics (default fast path).
  - `diagnostics/run_observability_summary.json` – Authoritative observability rollup (stage verdicts, cohort funnel counts, audits); drives terminal **Run Health** and `run_evidence_index.md` (`paths.run_observability_summary_json` in that JSON).
  - `run_evidence_index.md` – Best first human-facing summary for a completed run.
  - `diagnostics/artifact_inventory.json` – Run-scoped output inventory and lifecycle classification.
  - `model_comparison_summary.xlsx` - Optional ranked model workbook export.
  - Feature matrix with AV and permission-based statistics.

---

## Configuration

### Database (split Erebus + Permission Intel)

ObsidianDroid reads **operational sample metadata, VirusTotal aggregates, and catalog fields** from the primary Erebus database (illustrative schema `sample_source_db`). It reads **live Android permission intelligence** (`android_permission_*` tables) from the Permission Intel database (illustrative name `permission_source_db`). Both schemas normally live on the same MySQL/MariaDB server; queries use the credentials below for both connections.

Override via environment variables (recommended for deployment):

| Variable | Purpose |
| --- | --- |
| `OBSIDIAN_DB_HOST`, `OBSIDIAN_DB_PORT` | Server host and port |
| `OBSIDIAN_DB_USER`, `OBSIDIAN_DB_PASSWORD` | Credentials (same user typically has `SELECT` on both schemas) |
| `OBSIDIAN_DB_OPTION_FILE` | Alternative explicit private MariaDB client option file (mode `0600`) for both upstream source schemas |
| `OBSIDIAN_DB_NAME` | Primary Erebus schema |
| `OBSIDIAN_PERMISSION_INTEL_DB_HOST`, `OBSIDIAN_PERMISSION_INTEL_DB_PORT` | Optional Permission Intel server override |
| `OBSIDIAN_PERMISSION_INTEL_DB_USER`, `OBSIDIAN_PERMISSION_INTEL_DB_PASSWORD` | Optional dedicated Permission Intel reader credentials |
| `OBSIDIAN_PERMISSION_INTEL_DB_OPTION_FILE` | Optional dedicated private MariaDB client option file (mode `0600`) |
| `OBSIDIAN_PERMISSION_INTEL_DB_NAME` | Permission Intel schema (illustrative name `permission_source_db`) |

Consult `obsidiandroid.database.db_config` for runtime defaults; the schema names here are placeholders. Cross-schema SQL (for example joining `malware_sample_catalog` to `android_permission_obs_sample`) fully qualifies both schema names so ObsidianDroid does not rely on live `android_permission_*` tables inside the primary DB.

Quick connectivity check (requires network access to the DB):

```bash
python -m obsidiandroid.database.split_db_health
```

The versioned shadow contract has a separate bounded, credential-redacted
readiness probe. It checks the approved read-only account, accepted catalog
gate, exact-case lookup, protection flags, split relations, and source evidence
using `SELECT` only:

```bash
python -m obsidiandroid.database.permission_intel_v1 --json
```

### Pipeline and model settings

Model and pipeline settings can be customized in `config/settings/*.py` (re-exported by `config/app_config.py`):
- Train/test split, random seed, estimator hyperparameters.
- Split grouping: a profile may set `split_grouping: package` to hold out whole package-name groups (sha256 fallback) with a label-stratified grouped split; the default `none` keeps the historical split so earlier runs replay unchanged.
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
- Permission-trends bundle: `WRITE_RUN_SCOPED_PERMISSION_TREND_ARTIFACTS` (in `config/settings/methodology.py`) emits run-stamped tables/figures next to `*.latest.*` peers. In **effective evidence mode**, the runner turns this on automatically unless the profile sets `runtime_overrides.WRITE_RUN_SCOPED_PERMISSION_TREND_ARTIFACTS`.
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

## Repository layout & migration status

The repo uses a **src layout**: installable code in **`src/obsidiandroid/`** and versioned SQL assets under repo-root **`database/`**. For a **full audit** of the root, CI/tooling maturity, and planned next steps (not everything fits in the tree diagram above), see **[`docs/ROOT_AND_STRUCTURE_AUDIT.md`](docs/ROOT_AND_STRUCTURE_AUDIT.md)**.

---

## Optional Tools

- `make ci-fast` – **`make doc-check`** + **`make verify`** + **`make ml-scan-strict`** (the GitHub fast lane).
- `make ci` – `make ci-fast` plus **`make verify-canonical`**; integration lanes are separate.
- `make setup` – Same as `./setup.sh`: create/update `.venv` and install `requirements.txt`.
- `make menu` – Same as `./run.sh`: interactive startup menu with `PYTHONPATH=src`.
- `make install-editable` – `pip install -e .` (run with venv active) so `import obsidiandroid` works outside pytest.
- `make tree-source` – Filtered source tree (install `tree`; run `make clean-bytecode` first for a clean view).
- `make ml-scan` or `python -m scripts.dev.run_ml_static_scan` – Scan the repo for accidental `.predict()` misuse (`--strict` fails on warnings).
- `make clean` / `make clean-bytecode` or `python scripts/dev/clean_bytecode_cache.py [path] --exclude venv` – Remove bytecode/logs.
- `python scripts/dev/data_fuzzer.py` – Generate large synthetic datasets for robustness and stress testing.

---

## Running Tests

After installing dependencies, run the **default fast suite** (recommended for local loops):

```bash
make ci-fast                  # doc-check + verify + strict ML scan
make ci                       # fast gate + canonical closure
# or, without the ML strict scan:
make verify
# or run pytest only (after import checks manually if needed):
pytest -q
./scripts/dev/run_tests.sh
make test
```

**`make doc-check`** scans key docs for removed phantom paths
(`scripts/dev/check_doc_hygiene.py`). **`make verify`** runs the import-surface
check (`scripts/dev/check_import_surface.py`) and then the fast suite.
**`make ci-fast`** adds the strict ML scan; **`make ci`** also validates canonical
closure. Integration lanes are separate (`make verify-integration` and
`make verify-pipeline-integration`). The fast suite excludes modules tagged
`slow` (see `pyproject.toml` and `tests/conftest.py`).

For the **complete** suite (CI / pre-merge):

```bash
./scripts/dev/run_tests_full.sh
# or
make test-full
```

---

## Contributing

Contributions are welcome! To propose enhancements, bug fixes, or new features:
- Fork the repository and submit a pull request.
- Please include tests and documentation for new features.
- Before opening a PR, run **`make ci-fast`** (or at least **`make verify`**)
  from the repo root with your venv active and **`pip install -e .`**. Run
  **`make ci`** when canonical closure matters and the relevant integration
  lane for pipeline changes. The GitHub workflow runs these lanes separately.
- Layout and migration context: **[`docs/ROOT_AND_STRUCTURE_AUDIT.md`](docs/ROOT_AND_STRUCTURE_AUDIT.md)** and **[`docs/AGENTS.md`](docs/AGENTS.md)**. **Breaking change:** repo-root **`data_inspect/`** and **`devtools/`** were removed; use **`scripts.diagnostics`** and **`scripts.dev`** instead (see **`docs/STRUCTURE_MIGRATION_PLAN.md`** → Pass 24).
- Open issues for questions, ideas, or feedback.

---

## License

MIT License (see [LICENSE](LICENSE)).
For academic and research use only. Commercial use requires written permission.
Handle malware data responsibly and comply with VirusTotal terms and all applicable laws.

---


### Operational artifact assessments (V1, local sidecar)

The bounded assessment path consumes a frozen exact-SHA evidence snapshot and
stores immutable revisions in an explicitly selected **local SQLite file**.
It synthesizes existing governed evidence; it does not run a classifier or
infer benignness from missing AV detections. Production persistence is not enabled.

```bash
PYTHONPATH=src .venv/bin/python -m obsidiandroid.cli.assessment assess "$SHA256" \
  --snapshot /path/to/pilot_evidence.json --store /path/to/assessments.sqlite --json
PYTHONPATH=src .venv/bin/python -m obsidiandroid.cli.assessment current "$SHA256" \
  --store /path/to/assessments.sqlite
PYTHONPATH=src .venv/bin/python -m obsidiandroid.cli.assessment history "$SHA256" \
  --store /path/to/assessments.sqlite --json
```

An updated editable install also exposes `obsidiandroid-assess` with these same
arguments. `assess` writes only the selected local sidecar; it does not query
live databases. A hash outside the supplied snapshot returns `not_in_snapshot`,
which is distinct from a source-confirmed `not_found`. Conflicts retain candidates;
unresolved fields retain null values. Identical inputs reuse the current revision.

The shared `obsidiandroid.assessment.AssessmentService` provides `assess`,
`current` and `history` for the CLI and future API callers. See
[the V1 contract and persistence proposal](docs/OPERATIONAL_ASSESSMENT_V1.md).

### Operational assessment persistence (disposable validation)

The V1 assessment CLI supports SQLite `--store` or explicit MariaDB `--database`
plus a private `--db-option-file`. Use `assess`, `current`, or `history`, with
`--json` for the unchanged service contract. MariaDB never auto-creates schema.
Migration 0006 adds immutable operational revisions independently of model results;
production activation remains a separate authorized step. See
[the assessment contract](docs/OPERATIONAL_ASSESSMENT_V1.md#mariadb-persistence)
for commands, grants, transaction semantics, and opt-in live tests.

Assessment review now includes bounded `history --limit N --after-revision R`,
`by-id`, and `compare BEFORE_ID --against AFTER_ID`. The read-only
`obsidiandroid-assess-doctor` checks schema definitions and bounded exact-artifact
integrity, with explicit partial results. See
[review and health commands](docs/OPERATIONAL_ASSESSMENT_V1.md#review-and-read-only-health-checks).

### Approved PI V2 evidence

Use `./run.sh pi-v2 inspect --export /private/approved/EXACT_1813_EXPORT.json`
for anchored read-only inspection. `./run.sh pi-v2 features` additionally
requires `--training-ids` for an existing frozen split and checks in-memory
feature construction without model training. See
[`PI V2 deployment and commands`](docs/permission_v2_research_export_candidate.md).

The catalog profile readiness preview checks legacy observation-table counts.
If that table is not visible to its connection, those counts remain unavailable;
this does not establish whether an independently approved PI V2 export is usable.
Catalog-wide profiles do not automatically substitute the exact export cohort.
The Full pipeline persistence choice controls Core result persistence, not PI
source selection: exploratory/read-only runs can still train models and write
local output files.

In **Run Analysis**, the run modes describe their work (full analysis, one model,
selected stages, or feature extraction). The execution-profile screen labels saved
results with their previous run ID; the source counts shown after selection are
separate current inventory. A successful cohort preflight is only a viability
check, not proof that all feature inputs are available.

Full analysis then asks **Save analysis results**: **Run with local files only**
or **Run with local files + Core database results**. Both execute the configured
analysis and model training; the second explicitly enables Core persistence.
**Cancel run** exits without starting either operation.

The all-APK exploratory profile explicitly requires Permission Intel features.
Its legacy permission-access gate is checked before loading cohort data, both
from the menu and from direct pipeline invocation. A blocked or unavailable gate
stops the run during preflight; it does not disable features, grant access, or
substitute the smaller approved PI V2 export. Feature extraction still rechecks
the gate. Exploratory catalog summaries are labeled as exploration, not a
publication benchmark.

Permission fusion summaries count both legacy and source-bound occurrence
features, including PI V2 unresolved tokens. Evidence-status columns do not
count as permission features or positive feature signal. A valid feature export
and fusion check alone does not validate model splits or classification results.

### Explore data without starting analysis

Run `./run.sh`, then choose **1 — Explore Android data**. The five screens show
live dataset counts, paginated family/type distributions, label quality,
AV/permission coverage, and exact sample lookup. Browsing uses read-only source
transactions and does not train models or alter run slots. Counts describe Android
APKs with dates and registry matches, before profile time/support/label gates;
they are not training eligibility. Saved runs remain under main menu **3**.

For PI coverage, enter the path to the independently approved export when prompted,
or set `OBSIDIANDROID_EXPLORER_PI_V2_EXPORT` for the menu process. This selects a
file, not an approval: the installed root-controlled anchor is still mandatory.
Uncovered identities have unknown permission evidence. Provider-reported unresolved
occurrences are not verified manifest permissions or training authorization.

Main menu **2 — Run malware classification** offers family and malware-type
classification, with the full profile catalog and execution modes under **3 —
Advanced profiles and execution modes**. The specialized frozen cohort YAML remains
a contract, not an ordinary runnable profile. Main menu **4** retains research
checks; **5** retains maintenance, including Clear screen. Scientific acceptance,
PI coverage/authority, nested CV and preprocessing limitations remain separate
from source preflight and UI readiness. See [experiment integrity](docs/experiment_split_integrity.md).

### Minnesota time display

Console statistics, report tables and new text-log entries display both Minnesota
local time (`America/Chicago`) and UTC, using 12-hour clocks without seconds.
CST/CDT is resolved for each timestamp, including historical and future dates.
For example: `Oct 17, 2026 · 9:00 PM CDT | Oct 18, 2026 · 2:00 AM UTC`.

Exact UTC timestamps in machine-readable artifacts, database records, run IDs
and filenames retain their precision. Existing logs and frozen reports are not
rewritten. Date-only values remain dates. A timestamp without a known timezone
is not silently assumed to be Minnesota time; explicitly UTC fields are read as
UTC. The application currently has no event scheduler. Future scheduling UI must
use `America/Chicago` and explicitly resolve ambiguous/nonexistent local times.

### Classification overview and readiness

Main menu **2 — Run malware classification** opens family or type experiment
overviews. Merely entering an overview reads configuration; it does not run
preflight, train models or prepare/archive a run slot. Choose **1** to check
source prerequisites, **2** to inspect configuration, or **3** to request a run.
Starting reloads configuration and repeats preflight, then uses the existing
local-files/Core-results confirmation. **0** backs out without execution.
The overview is shown once unless configuration changes. After a failed check,
option **3** becomes **Why analysis is unavailable**, showing only the required
blockers without retrying queries. Option **1** explicitly rechecks readiness;
every subsequent start still runs fresh checks before confirmation.
For the major-family profile, option **1** also reports a bounded live metadata
population and AV-row coverage even when permissions block execution. These
counts precede runtime dataset/feature/split admission; unavailable counts are
shown as unknown. Non-PI training now also rejects misordered label identities
and refuses fallback when group or temporal isolation was explicitly requested.

The separate **dev_av_only_recorded_family** development workflow reads a frozen,
digest-verified local Erebus report snapshot through
`python -m obsidiandroid.modeling.av_only_experiment`. It defaults to plan-only;
`--train` explicitly requests one Logistic Regression fit. Required arguments are
`--snapshot`, `--snapshot-sha256` and `--output` (a new directory outside this
repository). It does not use the benchmark's run slot or database persistence.
It requires reviewed recorded-label provenance, coherent hash-bound AV reports,
at least 20 samples and four package/signer/fingerprint components per family,
and at least 10 train / 5 test samples in the first fixed group-stratified fold.
Only train-fitted AV observation/detection features are admitted; CV, tuning,
resampling and permission features are excluded by this development contract.
This measures reconstruction of recorded attribution with shared AV-source
dependence, not independent malware ground truth or paper reproduction.

READY means only the named check passed. Profile viability is not a measured
training cohort, feature-coverage audit, split acceptance or scientific approval.
Unmeasured cohort counts, eligible classes and features show NOT EVALUATED.
Required failed or unavailable prerequisites prevent starting from this overview.
PI V2 split binding is implemented, but approval v1 still does not authorize
target-specific model fitting. The overview preserves that blocker and all
legacy permission gates. Classification option **3 — Compare models and features** opens the existing
family/type multi-model profiles or the Random Forest development ablation
profile. Ablation arms include binary AV, vendor semantics with family/type
exclusions, raw/grouped permissions and fused inputs; this is not an AV-only
permission bypass. Option **4 — Other experiments and tests** retains historical
profiles, sensitivity studies, development/smoke modes and stage cutoffs.
Advanced training modes also check source prerequisites and request an explicit
continuation before execution. All existing scientific constraints remain.

Deployment identifiers in this guide are illustrative placeholders. Configure actual schema and account names locally; these documentation changes do not change runtime defaults.
