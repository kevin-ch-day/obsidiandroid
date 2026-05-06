import pandas as pd
from obsidiandroid.feature_engineering.pattern_analysis import (
    feature_correlation_summary,
    detect_outliers,
    compute_pca_features,
)

def test_feature_correlation_summary_runs():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [2, 4, 6], "c": [1, 1, 1]})
    corr = feature_correlation_summary(df, verbose=False)
    assert isinstance(corr, pd.DataFrame)
    assert set(corr.columns) >= {"a", "b"}

def test_detect_outliers_basic():
    df = pd.DataFrame({"a": [1, 2, 100], "b": [1, 1, 1]})
    out = detect_outliers(df, ["a", "b"], z_thresh=1.0, verbose=False)
    assert len(out) == 1

def test_compute_pca_features_shape():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [2, 4, 6]})
    result = compute_pca_features(df, n_components=1, verbose=False)
    assert "PCA_1" in result.columns
