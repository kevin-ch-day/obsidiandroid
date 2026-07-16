"""Regression coverage for the legacy structured-label wrapper."""

from obsidiandroid.labeling import label_builder_wrapper


def test_structured_label_builder_is_importable() -> None:
    """Its evaluated DataFrame return annotation must not break import."""
    assert callable(label_builder_wrapper.build_structured_label_output)
