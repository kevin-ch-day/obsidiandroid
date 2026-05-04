"""Stable entrypoint for automation and scripts that invoke the full pipeline.

Same object as :func:`obsidiandroid.pipeline.run_pipeline` (facade over
``analysis.pipeline.runner.run_pipeline``). CLI and tests often use
``from main import run_pipeline``; all resolve to the same implementation.
"""

from __future__ import annotations

from obsidiandroid.pipeline import run_pipeline

__all__ = ["run_pipeline"]
