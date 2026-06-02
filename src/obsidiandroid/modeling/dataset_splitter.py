# Filename: obsidiandroid/modeling/dataset_splitter.py
# Purpose : Utility for balanced train/test splitting with minimal per-class support

from __future__ import annotations

from collections import Counter
from typing import Tuple

import numpy as np
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

    y_series = y if isinstance(y, pd.Series) else pd.Series(y, index=X.index)
    singleton_classes = {cls for cls, count in counts.items() if count < 2}
    singleton_mask = y_series.isin(singleton_classes)

    if singleton_classes:
        du.print_warning(
            "[SPLIT] balanced_train_test_split: forcing singleton classes into train and "
            "stratifying the remaining classes."
        )

    X_forced_train = X.loc[singleton_mask]
    y_forced_train = y_series.loc[singleton_mask]
    X_remaining = X.loc[~singleton_mask]
    y_remaining = y_series.loc[~singleton_mask]

    remaining_counts = Counter(y_remaining)
    min_support = min(remaining_counts.values()) if remaining_counts else 0
    stratify_y = y_remaining if min_support >= 2 else None
    if stratify_y is None and len(remaining_counts) > 1:
        du.print_warning(
            "[SPLIT] balanced_train_test_split: stratification disabled on the non-singleton "
            "subset because at least one remaining class has fewer than 2 samples."
        )

    if X_remaining.empty:
        X_train = X_forced_train.copy()
        X_test = X.iloc[0:0].copy()
        y_train = y_forced_train.copy()
        y_test = y_series.iloc[0:0].copy()
        return X_train, X_test, y_train, y_test

    X_train_core, X_test, y_train_core, y_test = train_test_split(
        X_remaining,
        y_remaining,
        test_size=required_test_size,
        stratify=stratify_y,
        random_state=random_state,
    )

    if not X_forced_train.empty:
        X_train = pd.concat([X_train_core, X_forced_train], axis=0)
        y_train = pd.concat([y_train_core, y_forced_train], axis=0)
        order = np.argsort(X_train.index.to_numpy())
        X_train = X_train.iloc[order]
        y_train = y_train.iloc[order]
    else:
        X_train = X_train_core
        y_train = y_train_core

    return X_train, X_test, y_train, y_test
