"""Sanity checks for ``utils.pipeline_entry`` re-exports."""

from __future__ import annotations

from obsidiandroid.pipeline import runner as runner_mod
from utils import pipeline_entry


def test_pipeline_entry_run_pipeline_is_runner_impl() -> None:
    assert pipeline_entry.run_pipeline is runner_mod.run_pipeline
