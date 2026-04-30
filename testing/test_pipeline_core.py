import pandas as pd
from ml_classification.training import pipeline_core


def test_align_data_returns_series():
    features = pd.DataFrame({'feat': [1, 2]}, index=['s1', 's2'])
    labels = pd.DataFrame({'sample_id': ['s1', 's2'], 'family_name': ['A', 'B']})
    f, l = pipeline_core.align_data(features, labels)
    assert isinstance(l, pd.Series)
    assert list(f.index) == ['s1', 's2']

