import pandas as pd
from ml_classification.engine_weights import classification_weight_utils as cwutils
from ml_classification.engine_weights import compute_reliability_score as crs


def test_zscore_columns():
    df = pd.DataFrame({'A': [1, 2, 3, 4]})
    df = cwutils.zscore_columns(df, {'A': 'A_z'})
    assert 'A_z' in df.columns
    assert abs(df['A_z'].mean()) < 1e-6
    assert round(df['A_z'].iloc[0], 4) == round((1 - df['A'].mean())/df['A'].std(), 4)


def test_compute_reliability_with_zscore():
    data = {
        'Detection Rate (Norm)': [0.8],
        'Coverage % (Norm)': [0.7],
        'Tier Score (Norm)': [0.6],
        'Detection Rate (Z)': [0.5],
        'Coverage % (Z)': [0.2],
        'Tier Score (Z)': [0.1],
    }
    df = pd.DataFrame(data)
    result = crs.compute_reliability(df.copy(), verbose=False)
    assert 'Reliability' in result.columns
    assert result['Reliability'].iloc[0] > 0
