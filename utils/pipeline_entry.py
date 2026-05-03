"""Stable entrypoint for automation and scripts that invoke the full pipeline.

Prefer this over duplicating ``from analysis.pipeline.runner import run_pipeline`` in
many places. CLI and tests continue to use ``from main import run_pipeline``; both
resolve to the same implementation.
"""

from __future__ import annotations

from analysis.pipeline.runner import run_pipeline

__all__ = ["run_pipeline"]
