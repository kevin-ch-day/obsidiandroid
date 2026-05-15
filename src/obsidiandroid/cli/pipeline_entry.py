"""Stable entrypoint for automation and scripts that invoke the full pipeline.

Same object as :func:`obsidiandroid.pipeline.run_pipeline`. Legacy
``analysis.pipeline.runner.run_pipeline`` and ``from main import run_pipeline``
surfaces remain compatibility aliases to the same implementation.
"""

from __future__ import annotations

from obsidiandroid.pipeline import run_pipeline

__all__ = ["run_pipeline"]
