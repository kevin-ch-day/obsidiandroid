"""Grid-search, cross-validation, and calibration configuration."""

ENABLE_RF_GRID_SEARCH = False
RF_PARAM_GRID = {
    "n_estimators": [150, 200],
    "max_depth": [12, 20],
    "max_features": ["sqrt"],
    "min_samples_split": [2, 4],
    "min_samples_leaf": [1, 2],
    "oob_score": [False, True],
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
    "n_estimators": [200, 300],
    "max_depth": [4, 6, 8],
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

ENABLE_PROBABILITY_CALIBRATION = False
CALIBRATION_METHOD = "sigmoid"
CALIBRATION_HOLDOUT = 0.15
