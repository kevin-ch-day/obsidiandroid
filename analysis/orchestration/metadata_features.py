"""Compatibility re-export for metadata feature helpers.

Canonical implementation lives in :mod:`analysis.pipeline.sample_preparation`
(used by :mod:`analysis.pipeline.stage_feature_enrichment`). Import from there
in new code.
"""

from __future__ import annotations

from analysis.pipeline.sample_preparation import (  # noqa: F401
    build_metadata_feature_frame,
    extract_vt_tag_count,
)

__all__ = ["build_metadata_feature_frame", "extract_vt_tag_count"]
