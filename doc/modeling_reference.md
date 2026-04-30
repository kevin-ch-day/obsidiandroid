# Modeling and Evaluation Reference

This reference summarizes the machine learning components that ship with ObsidianDroid, their configuration levers, and the artefacts they produce. Use it to choose an appropriate estimator for a deployment, extend the modeling library, or interpret benchmarking outputs.

## Feature Families

ObsidianDroid assembles heterogeneous features that capture AV behaviour and Android application traits. Builders live in `analysis/feature_engineering/` and can be toggled in `config/app_config.py`.

| Feature Group | Description | Example Columns |
| --- | --- | --- |
| Vendor consensus | Detection ratios, quorum counts, disagreement scores derived from VirusTotal engines. | `vt_detect_ratio`, `vt_consensus_score`, `top_vendor_flag`. |
| Vendor reliability | Engine-specific weights and trust bands computed from historical accuracy. | `engine_weight_<vendor>`, `engine_precision_<vendor>`. |
| Permission signals | Binary permission usage flags and risk categories extracted from manifests. | `perm_SEND_SMS`, `perm_READ_CONTACTS`, `perm_group_FINANCIAL`. |
| Temporal context | Submission recency, first-seen deltas, rolling detection velocity. | `days_since_first_seen`, `detections_last_30d`. |
| Custom enrichments | Optional features derived from sandbox runs or static analysis. | `sandbox_behavior_score`, `packer_hint`. |

## Supported Estimators

| Estimator | Module | Strengths | Key Settings |
| --- | --- | --- | --- |
| Random Forest | `ml_classification/models/random_forest.py` | Handles high-dimensional sparse features, stable baseline. | `n_estimators`, `max_depth`, `class_weight`. |
| Support Vector Machine | `ml_classification/models/svm.py` | Strong margins for well-separated families; requires scaling. | `kernel`, `C`, `gamma`. |
| Logistic Regression | `ml_classification/models/logistic_regression.py` | Fast training, probabilistic outputs, interpretable weights. | `penalty`, `C`, `solver`. |
| XGBoost | `ml_classification/models/xgboost.py` | Captures complex non-linear interactions with regularization. | `max_depth`, `learning_rate`, `subsample`. |
| Gradient Boosting | `ml_classification/models/gradient_boosting.py` | Strong performance on tabular data with modest tuning. | `n_estimators`, `max_depth`, `learning_rate`. |
| Voting Ensemble | `ml_classification/ensembles/voting.py` | Aggregates base estimators for robustness. | `weights`, component model selection. |

To introduce a new model, add its factory function to `ml_classification/model_factory.py`, define hyperparameters in `config/model_params/`, and cover it with tests under `tests/ml_classification/`.

## Hyperparameter Management

- Default parameter grids live under `config/model_params/` and are loaded through `utils/config_loader.py`.
- `model_tuning.py` orchestrates grid and random search routines. Use the `--estimator` flag to scope tuning runs.
- Persist tuned parameters back into configuration files and document rationale in commit messages or the operations logbook.

## Evaluation Outputs

Running `main.py` or `model_tuning.py` emits artefacts in `output/` that analysts can review:

- `model_comparison_summary.xlsx` – ranking of estimators by F1, precision, recall, ROC-AUC.
- `family_metrics/` – per-family confusion matrices and class-specific metrics in CSV format.
- `feature_importance/` – SHAP and permutation importance exports for supported models.
- `final_classification_labels.xlsx` – canonical label recommendations with consensus context.

Use `analysis/evaluation/report_builder.py` to regenerate consolidated PDF/HTML reports for stakeholder distribution.

## Operational Considerations

- **Class imbalance:** Apply stratified sampling or class weight adjustments in `config/app_config.py` when onboarding new datasets.
- **Concept drift:** Schedule quarterly retraining and compare F1 deltas; capture findings in the operations log.
- **Explainability:** Enable SHAP exports when regulators require model transparency, and store artefacts securely.
- **Resource planning:** GPU acceleration is optional—most runs fit comfortably on a 16-core CPU with 32 GB RAM.

## Related Documentation

- [`architecture.md`](architecture.md) – structural overview of where each modeling component executes.
- [`developer_guide.md`](developer_guide.md) – coding standards and validation steps when modifying models.
- [`user_guide.md`](user_guide.md) – instructions for invoking training and interpreting outputs.

