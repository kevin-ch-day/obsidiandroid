import pandas as pd
from scripts.dev import data_fuzzer


def test_generate_fuzz_data_shapes():
    df, labels = data_fuzzer.generate_fuzz_data(n_samples=50, n_features=10, n_classes=4, random_state=1)
    assert isinstance(df, pd.DataFrame)
    assert isinstance(labels, pd.Series)
    assert df.shape == (50, 10)
    assert len(labels) == 50
    assert set(labels.unique()) <= set(range(4))
