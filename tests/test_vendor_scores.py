import pandas as pd
from analysis.feature_engineering.compute_vendor_scores import (
    run_score_analysis,
    print_score_distribution,
)


def _sample_df():
    return pd.DataFrame({
        "Vendor": ["a", "b"],
        "Enrichment Score": [50, 60],
        "Family Match Accuracy (%)": [70, 80],
        "Detection Diversity": [10, 12],
        "Unknown Parsed (%)": [5, 10],
        "Unique Labels": [15, 20],
        "Generic Family Ratio": [0.1, 0.2],
        "Avg Genericity Score": [5, 10],
    })


def test_run_score_analysis_basic():
    df = _sample_df()
    scored = run_score_analysis(df, verbose=False)
    assert "Final ML Score" in scored.columns
    assert len(scored) == 2


def test_print_score_distribution_no_error(capsys):
    df = run_score_analysis(_sample_df(), verbose=False)
    print_score_distribution(df)
    captured = capsys.readouterr()
    assert "Score Distribution" in captured.out
