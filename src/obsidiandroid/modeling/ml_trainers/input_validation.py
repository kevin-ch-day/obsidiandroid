"""Numeric input validation shared by the logistic and SVM trainers."""

import numpy as np


def validate_numeric_training_inputs(X_train, y_train):
    """Basic sanity checks for training data."""
    if X_train is None or len(X_train) == 0:
        raise ValueError("X_train is missing or empty.")
    if y_train is None or len(y_train) == 0:
        raise ValueError("y_train is missing or empty.")
    if len(X_train) != len(y_train):
        raise ValueError(
            f"X_train and y_train length mismatch: {len(X_train)} != {len(y_train)}"
        )
    x_values = np.asarray(X_train)
    y_values = np.asarray(y_train)
    if np.isnan(x_values).any() or np.isnan(y_values).any():
        raise ValueError("NaN values detected in training data.")
