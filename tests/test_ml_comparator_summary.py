"""Tests for model comparison summary helpers."""

from ml_classification.ml_utils import ml_comparator_summary


def test_model_display_name_aliases() -> None:
    """Known model aliases should be compact and stable."""
    assert ml_comparator_summary._model_display_name("logistic_regression") == "log_reg"  # pylint: disable=protected-access
    assert ml_comparator_summary._model_display_name("balanced_random_forest") == "bal_rf"  # pylint: disable=protected-access


def test_model_display_name_truncates_unknown() -> None:
    """Unknown long model names should be ellipsized."""
    label = ml_comparator_summary._model_display_name("a_very_long_custom_model_name", max_len=10)  # pylint: disable=protected-access
    assert len(label) <= 10
    assert label.endswith("…")
