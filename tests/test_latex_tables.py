"""Tests for publication-ready LaTeX table formatting helpers."""

from __future__ import annotations

import pandas as pd

import obsidiandroid.reporting.latex_tables as latex_tables


def test_model_comparison_formatting_bolds_best_and_rounds() -> None:
    """Model table should normalize names, round metrics, and bold best rank."""
    raw = pd.DataFrame(
        [
            {
                "Model": "random_forest",
                "Accuracy": 0.9761,
                "Precision": 0.9751,
                "Recall": 0.9761,
                "F1-Score": 0.9750,
                "Macro F1-Score": 0.9530,
                "Rank": 1,
            },
            {
                "Model": "xgboost",
                "Accuracy": 0.9681,
                "Precision": 0.9684,
                "Recall": 0.9681,
                "F1-Score": 0.9665,
                "Macro F1-Score": 0.9412,
                "Rank": 2,
            },
        ]
    )
    out = latex_tables.build_model_comparison_table(raw)
    assert list(out.columns) == ["Model", "Accuracy", "Precision", "Recall", "F1", "Macro-F1", "Rank"]
    assert out.iloc[0]["Model"] == r"\textbf{Random Forest}"
    assert out.iloc[1]["Model"] == "XGBoost"
    assert out.iloc[0]["Accuracy"] == "0.976"
    assert out.iloc[1]["Macro-F1"] == "0.941"


def test_feature_ablation_exports_full_metrics_context() -> None:
    """Ablation table should include feature set, model, and core metrics."""
    raw = pd.DataFrame(
        [
            {
                "experiment": "vendor_permissions_fused",
                "model": "random_forest",
                "accuracy": 0.9761,
                "macro_precision": 0.9584,
                "macro_recall": 0.9568,
                "macro_f1_score": 0.9566,
            }
        ]
    )
    out = latex_tables.build_feature_ablation_table(raw)
    assert list(out.columns) == [
        "Feature Set",
        "Model",
        "Accuracy",
        "Macro Precision",
        "Macro Recall",
        "Macro-F1",
    ]
    assert out.iloc[0]["Feature Set"] == "Vendor Permissions Fused"
    assert out.iloc[0]["Model"] == "Random Forest"
    assert out.iloc[0]["Macro-F1"] == "0.957"


def test_cohort_summary_formats_integers_and_percentages() -> None:
    """Cohort summary should avoid float-like integers and render percentages."""
    raw = pd.DataFrame(
        [
            {"Metric": "Total Samples", "Value": 1226.0},
            {"Metric": "Unique Families", "Value": 39.0},
            {"Metric": "Largest Family Share", "Value": 0.1607},
            {"Metric": "Time Window End", "Value": 2026.0},
        ]
    )
    out = latex_tables.build_cohort_summary_table(raw)
    assert out.iloc[0]["Value"] == "1226"
    assert out.iloc[1]["Value"] == "39"
    assert out.iloc[2]["Value"] == "16.1%"
    assert out.iloc[3]["Value"] == "2026"


def test_dangerous_stats_table_uses_readable_labels_and_no_blanks() -> None:
    """Dangerous stats table should avoid internal tokens and blank cells."""
    raw = pd.DataFrame(
        [
            {
                "metric": "dangerous_count_strict",
                "group_a": "all",
                "group_b": "all",
                "statistic": 149.7427,
                "p_value": 1.5e-30,
                "p_value_fdr_bh": 1.5e-30,
                "effect_size": None,
                "effect_size_name": "epsilon_squared",
                "test_type": "kruskal_wallis",
            }
        ]
    )
    out = latex_tables.build_dangerous_stats_table(raw)
    assert out.iloc[0]["Metric"] == "Dangerous Permission Count"
    assert out.iloc[0]["Test"] == "Kruskal-Wallis"
    assert out.iloc[0]["Effect Name"] == "Epsilon-Squared"
    assert out.iloc[0]["Effect Size"] == "--"
