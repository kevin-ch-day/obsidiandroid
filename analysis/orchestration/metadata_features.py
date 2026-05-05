"""Compatibility re-export for metadata feature helpers.

Canonical implementation lives behind :mod:`obsidiandroid.pipeline.sample_preparation`.
Import from there in new code.
"""

from __future__ import annotations

from obsidiandroid.pipeline import sample_preparation

build_metadata_feature_frame = sample_preparation.build_metadata_feature_frame
extract_vt_tag_count = sample_preparation.extract_vt_tag_count

__all__ = ["build_metadata_feature_frame", "extract_vt_tag_count"]
