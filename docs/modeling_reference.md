# Modeling and Evaluation Reference

This reference summarizes the machine learning components that ship with ObsidianDroid, their configuration levers, and the artefacts they produce. Use it to choose an appropriate estimator for a deployment, extend the modeling library, or interpret benchmarking outputs.

## Feature Families

ObsidianDroid assembles heterogeneous features that capture AV behaviour and Android application traits. Canonical builders live in `src/obsidiandroid/feature_engineering/` (legacy `analysis.feature_engineering.*` is an identity shim) and can be toggled in `config/app_config.py`.

| Feature Group | Description | Example Columns |
| --- | --- | --- |
| Vendor consensus | Detection ratios, quorum counts, disagreement scores derived from VirusTotal engines. | `vt_detect_ratio`, `vt_consensus_score`, `top_vendor_flag`. |
| Vendor reliability | Engine-specific weights and trust bands computed from historical accuracy. | `engine_weight_<vendor>`, `engine_precision_<vendor>`. |
| Permission signals | Binary permission usage flags and risk categories extracted from manifests. | `perm_SEND_SMS`, `perm_READ_CONTACTS`, `perm_group_FINANCIAL`. |
| Temporal context | Submission recency, first-seen deltas, rolling detection velocity. | `days_since_first_seen`, `detections_last_30d`. |
| Custom enrichments | Optional features derived from sandbox runs or static analysis. | `sandbox_behavior_score`, `packer_hint`. |

## Supported Estimators

Training entrypoints live in **`ml_classification/training/model_trainer_factory.py`** (factory) and **`ml_classification/training/training_helpers.py`** (`get_model_trainer`). Trainer implementations:

| Estimator | Trainer module | Strengths | Key settings (see trainer defaults) |
| --- | --- | --- | --- |
| Random Forest | `ml_classification/training/ml_trainers/random_forest.py` | High-dimensional sparse features; stable baseline. | `n_estimators`, `max_depth`, `class_weight`. |
| Balanced Random Forest | `ml_classification/training/ml_trainers/balanced_random_forest.py` | Imbalance-aware RF variant (`imblearn`). | Same family as RF + imbalance defaults. |
| Support Vector Machine | `ml_classification/training/ml_trainers/svm.py` | Strong margins when classes separate well; scaling used in helpers. | `kernel`, `C`, `gamma`. |
| Logistic Regression | `ml_classification/training/ml_trainers/logistic_regression.py` | Fast, probabilistic outputs, interpretable weights. | `penalty`, `C`, `solver`. |
| XGBoost | `ml_classification/training/ml_trainers/xgboost.py` | Non-linear interactions with regularization. | `max_depth`, `learning_rate`, `subsample`. |

There is **no** separate `ml_classification/models/` package or sklearn **GradientBoosting** / **Voting** wrappers in-tree today—extend **`training_helpers.get_model_trainer`** and add a trainer module if you introduce new estimators.

To introduce a new model, wire it through **`model_trainer_factory.py`** / **`get_model_trainer`**, define hyperparameters in **`config/model_params/`**, and cover it with tests under **`tests/`**.

## Hyperparameter Management

- Default parameter grids live under **`config/model_params/`** and are consumed via **`config/`** / **`config/settings/`** and **`config/app_config.py`** (there is no `utils/config_loader.py` in this repository).
- `python -m obsidiandroid.evaluation.model_tuning` exposes `tune_models` / `print_summary` for experimental sweeps; production grid search is driven through `ml_classification` trainers and `config/model_params/`.
- Persist tuned parameters back into configuration files and document rationale in commit messages or the operations logbook.

## Evaluation Outputs

Running `main.py` or `python -m obsidiandroid.evaluation.model_tuning` emits artefacts in `output/` that analysts can review:

- `model_comparison_summary.xlsx` – ranking of estimators by F1, precision, recall, ROC-AUC.
- `family_metrics/` – per-family confusion matrices and class-specific metrics in CSV format.
- `feature_importance/` – SHAP and permutation importance exports for supported models.
- `final_classification_labels.xlsx` – canonical label recommendations with consensus context.

Use **`ml_classification/reporting/ml_report_builder.py`** (and related reporting under **`ml_classification/reporting/`**) for consolidated evaluation summaries and exporter-driven artefacts under **`output/`**.

## Operational Considerations

- **Class imbalance:** Apply stratified sampling or class weight adjustments in `config/app_config.py` when onboarding new datasets.
- **Concept drift:** Schedule quarterly retraining and compare F1 deltas; capture findings in the operations log.
- **Explainability:** Enable SHAP exports when regulators require model transparency, and store artefacts securely.
- **Resource planning:** GPU acceleration is optional—most runs fit comfortably on a 16-core CPU with 32 GB RAM.

## Related Documentation

- [`architecture.md`](architecture.md) – structural overview of where each modeling component executes.
- [`developer_guide.md`](developer_guide.md) – coding standards and validation steps when modifying models.
- [`user_guide.md`](user_guide.md) – instructions for invoking training and interpreting outputs.

