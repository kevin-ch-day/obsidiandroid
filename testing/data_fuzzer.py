"""Utility to generate synthetic classification data for tests.

The generator wraps sklearn's ``make_classification`` and returns pandas
DataFrame/Series objects for convenient use in unit tests. It allows creating
larger datasets quickly to stress model trainers or other pipeline components.
"""

from typing import Tuple
import pandas as pd
from sklearn.datasets import make_classification


def generate_fuzz_data(
    n_samples: int = 1000,
    n_features: int = 20,
    n_classes: int = 3,
    class_sep: float = 1.0,
    random_state: int | None = None,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Return a feature DataFrame and label Series for testing.

    Parameters
    ----------
    n_samples : int, default 1000
        Number of samples to generate.
    n_features : int, default 20
        Number of feature columns.
    n_classes : int, default 3
        Number of label classes.
    class_sep : float, default 1.0
        Larger values yield more separated classes.
    random_state : int | None
        Optional seed for reproducibility.
    """
    X, y = make_classification(
        n_samples=n_samples,
        n_features=n_features,
        n_informative=n_features - 1,
        n_redundant=0,
        n_classes=n_classes,
        class_sep=class_sep,
        random_state=random_state,
    )
    return pd.DataFrame(X), pd.Series(y)


if __name__ == "__main__":
    df, labels = generate_fuzz_data()
    print(df.head())
    print(labels.value_counts())
