"""Convenience imports for trainer modules."""

from importlib import import_module

__all__ = [
    "random_forest_trainer",
    "balanced_random_forest_trainer",
    "logistic_regression_trainer",
    "svm_trainer",
    "xgboost_trainer",
]

for name in __all__:
    globals()[name] = import_module(f".{name}", __name__)

