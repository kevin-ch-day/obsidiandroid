"""Tests for publication-ready LaTeX table formatting helpers."""

from __future__ import annotations

import pandas as pd

import obsidiandroid.reporting.latex_tables as latex_tables
from ccncps2026_published_reference import (
    PUBLISHED_TABLE_II_RF,
    PUBLISHED_TABLE_II_XGB,
    PUBLISHED_TABLE_III_VENDOR_PERMS_RF,
)


def test_model_comparison_formatting_bolds_best_and_rounds() -> None:
    """Model table should normalize names, round metrics, and bold best rank.

    Inputs are published reference values (not reproduced by any retained run),
    used only as formatting fixtures.
    """
    raw = pd.DataFrame(
        [
            {"Model": "random_forest", **PUBLISHED_TABLE_II_RF, "Rank": 1},
            {"Model": "xgboost", **PUBLISHED_TABLE_II_XGB, "Rank": 2},
        ]
    )
    out = latex_tables.build_model_comparison_table(raw)
    assert list(out.columns) == ["Model", "Accuracy", "Precision", "Recall", "F1", "Macro-F1", "Rank"]
    assert out.iloc[0]["Model"] == r"\textbf{Random Forest}"
    assert out.iloc[1]["Model"] == "XGBoost"
    assert out.iloc[0]["Accuracy"] == "0.976"
    assert out.iloc[1]["Macro-F1"] == "0.941"


def test_feature_ablation_exports_full_metrics_context() -> None:
    """Ablation table should include feature set, model, and core metrics.

    The input row is a published reference value (not reproduced by any
    retained run), used only as a formatting fixture.
    """
    raw = pd.DataFrame(
        [
            {
                "experiment": "vendor_permissions_fused",
                "model": "random_forest",
                **PUBLISHED_TABLE_III_VENDOR_PERMS_RF,
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
