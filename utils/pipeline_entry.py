"""Stable entrypoint for automation and scripts that invoke the full pipeline.

Implementation lives in ``obsidiandroid.cli.pipeline_entry``; this module remains a
compatibility import path.
"""

from __future__ import annotations


from obsidiandroid.cli.pipeline_entry import run_pipeline

__all__ = ["run_pipeline"]
