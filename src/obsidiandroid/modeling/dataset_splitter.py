# Filename: obsidiandroid/modeling/dataset_splitter.py
# Purpose : Utility for balanced train/test splitting with minimal per-class support

from __future__ import annotations

from collections import Counter
from typing import Tuple

import pandas as pd
from sklearn.model_selection import train_test_split

from obsidiandroid.cli.ui import display as du


def balanced_train_test_split(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    test_size: float = 0.25,
    random_state: int = 42,
    min_test_per_class: int = 1,
    max_test_size: float = 0.5,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Perform a train/test split ensuring minimal test samples per class.

    Parameters
    ----------
    X : pd.DataFrame
        Feature matrix.
    y : pd.Series
        Encoded label vector.
    test_size : float, optional
        Desired fraction of data to reserve for testing.
    random_state : int, optional
        Seed for reproducible splits.
    min_test_per_class : int, optional
        Minimum number of samples for each class in the test split, when
        available.
    max_test_size : float, optional
        Upper bound to avoid excessive test sizes.

    Returns
    -------
    tuple
        (X_train, X_test, y_train, y_test)
    """

    counts = Counter(y)
    # Determine the minimal fraction needed to satisfy the test count
    required_fractions = []
    for _cls, count in counts.items():
        if count == 0:
            continue
        required = min(min_test_per_class, count) / count
        required_fractions.append(required)
    required_test_size = max([test_size] + required_fractions)
    required_test_size = min(max_test_size, required_test_size)

    min_support = min(counts.values()) if counts else 0
    stratify_y = y if min_support >= 2 else None
    if stratify_y is None and len(counts) > 1:
        du.print_warning(
            "[SPLIT] balanced_train_test_split: stratification disabled because at least one "
            "class has fewer than 2 samples."
        )

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=required_test_size,
        stratify=stratify_y,
        random_state=random_state,
    )
    return X_train, X_test, y_train, y_test
