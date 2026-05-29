"""Tests for model comparison ranking metric governance."""

from config import app_config
from obsidiandroid.evaluation import ml_comparator_summary


def test_compare_model_performance_ranks_by_macro_f1(monkeypatch) -> None:
    """Primary ranking should follow macro-F1 when configured."""
    monkeypatch.setattr(app_config, "MODEL_RANK_PRIMARY_METRIC", "macro_f1_score")

    results = {
        "model_a": {
            "evaluation": {
                "accuracy": 0.90,
                "precision": 0.91,
                "recall": 0.90,
                "f1_score": 0.92,
                "macro_f1_score": 0.70,
                "samples_tested": 100,
                "num_classes": 10,
                "accuracy_band": "T2",
            }
        },
        "model_b": {
            "evaluation": {
                "accuracy": 0.88,
                "precision": 0.89,
                "recall": 0.88,
                "f1_score": 0.89,
                "macro_f1_score": 0.80,
                "samples_tested": 100,
                "num_classes": 10,
                "accuracy_band": "T3",
            }
        },
    }

    summary_df = ml_comparator_summary.compare_model_performance(results)
    assert not summary_df.empty
    assert summary_df.iloc[0]["Model"] == "model_b"


def test_model_display_name_aliases() -> None:
    """Known model aliases should be compact and stable."""
    assert ml_comparator_summary._model_display_name("logistic_regression") == "log_reg"  # pylint: disable=protected-access
    assert ml_comparator_summary._model_display_name("balanced_random_forest") == "bal_rf"  # pylint: disable=protected-access


def test_model_display_name_truncates_unknown() -> None:
    """Unknown long model names should be ellipsized."""
    label = ml_comparator_summary._model_display_name(
        "a_very_long_custom_model_name",
        max_len=10,
    )  # pylint: disable=protected-access
    assert len(label) <= 10
    assert label.endswith("…")
