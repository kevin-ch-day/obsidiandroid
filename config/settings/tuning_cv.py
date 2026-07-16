"""Grid-search, cross-validation, and calibration configuration.

``GridSearchCV`` paths in ``obsidiandroid.modeling.ml_trainers`` use
:data:`CV_N_JOBS` and :data:`CV_AVOID_NESTED_PARALLELISM` via
:mod:`obsidiandroid.modeling.parallel_layout` so hyperparameter search matches
the nested-parallelism policy used in :func:`obsidiandroid.modeling.training_helpers.perform_cross_validation`.
"""

ENABLE_RF_GRID_SEARCH = False
# A five-fold grid search with fewer than 20 rows in a class is technically
# runnable but too unstable for publication-facing Macro-F1 selection. Keep
# this independent of cohort membership: diagnostic cohorts may retain rarer
# families while declining to tune them.
GRID_SEARCH_MIN_CLASS_SUPPORT = 20
# Bound queued GridSearchCV tasks so a large parameter grid does not duplicate
# the full training matrix once per worker.  ``2`` is deliberately conservative
# for broad-corpus and ablation profiles.
GRID_SEARCH_PRE_DISPATCH = 2
RF_PARAM_GRID = {
    "n_estimators": [150, 200],
    "max_depth": [12, 20],
    # Compare the baseline square-root rule with a modest wider feature view.
    # OOB is deliberately absent: it is a diagnostic, not a predictive tuning
    # parameter, and doubles grid fits without changing the CV objective.
    "max_features": ["sqrt", 0.20],
    "min_samples_split": [2, 4],
    "min_samples_leaf": [1, 2],
    "bootstrap": [True],
    "class_weight": ["balanced_subsample"],
}

ENABLE_SVM_GRID_SEARCH = False
SVM_PARAM_GRID = {
    "kernel": ["linear", "rbf"],
    "C": [0.1, 1.0, 10.0],
    "gamma": ["scale", "auto"],
}

ENABLE_LR_GRID_SEARCH = False
LR_PARAM_GRID = {
    "logisticregression__C": [0.1, 1.0, 10.0],
    "logisticregression__solver": ["lbfgs"],
}

ENABLE_XGB_GRID_SEARCH = False
XGB_PARAM_GRID = {
    # Keep every candidate at or below the medium-class guardrail (180).
    # The former 200/300 values both collapsed to 180 for a 34-class run.
    "n_estimators": [80, 140, 180],
    "max_depth": [4, 6],
    "learning_rate": [0.05, 0.1],
}

CV_FOLDS = 5
CV_REPEATS = 1
CV_N_JOBS = -1
ENABLE_CROSS_VALIDATION = True
ENABLE_CV_REBALANCING = True
ENABLE_CV_REBALANCING_XGBOOST = False
XGB_CV_MAX_FOLDS = 3
CV_AVOID_NESTED_PARALLELISM = True
XGB_EARLY_STOPPING_ROUNDS = 20
# The held-out test partition is evaluation-only.  Non-grid XGBoost training
# derives its early-stopping validation rows from the training partition.
XGB_EARLY_STOPPING_VALIDATION_FRACTION = 0.15

ENABLE_PROBABILITY_CALIBRATION = False
CALIBRATION_METHOD = "sigmoid"
CALIBRATION_HOLDOUT = 0.15
