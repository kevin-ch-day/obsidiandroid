"""Pipeline orchestration namespace (facade over ``analysis.pipeline``).

Re-exports stable, public symbols from :mod:`analysis.pipeline.runner` without
relocating implementation files. Prefer ``from obsidiandroid.pipeline import ...``
in new code.
"""

from __future__ import annotations

from analysis.pipeline.runner import (
    DIAGNOSTICS_DIR,
    PIPELINE_MAIN_LOGGER,
    PARSER_QUALITY_PATH,
    run_pipeline,
)

__all__ = [
    "DIAGNOSTICS_DIR",
    "PIPELINE_MAIN_LOGGER",
    "PARSER_QUALITY_PATH",
    "run_pipeline",
]
