"""Sanity checks for ``obsidiandroid.cli.pipeline_entry``."""

from __future__ import annotations

from obsidiandroid.cli import pipeline_entry
from obsidiandroid.pipeline import runner as runner_mod


def test_pipeline_entry_run_pipeline_is_runner_impl() -> None:
    assert pipeline_entry.run_pipeline is runner_mod.run_pipeline
