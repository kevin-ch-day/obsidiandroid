"""Tests for confusion matrix exporter backend safety."""

from __future__ import annotations

import matplotlib


def test_confusion_matrix_exporter_forces_agg_backend() -> None:
    """Confusion matrix exports should use a non-interactive backend."""
    import obsidiandroid.reporting.confusion_matrix_exporter  # noqa: F401 pylint: disable=import-outside-toplevel,unused-import

    backend = str(matplotlib.get_backend()).lower()
    assert "agg" in backend
