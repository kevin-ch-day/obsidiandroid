"""Propagate classifier-pipeline alignment attrition into run manifest context."""

from __future__ import annotations

from typing import Any

from config import app_config


def apply_training_alignment_attrition_to_manifest(manifest_context: dict[str, Any]) -> None:
    """Merge training-stage ``align_data`` attrition into ``manifest_context``.

    The runner's coarse alignment stage intersects features and labels by sample id only.
    Classifier training re-aligns with family-authority filtering; without this merge,
    observability and funnel artifacts under-report non-authoritative family drops.
    """
    stats = getattr(app_config, "RUNTIME_TRAINING_ALIGNMENT_ATTRITION_STATS", None)
    details = getattr(app_config, "RUNTIME_TRAINING_ALIGNMENT_ATTRITION_DETAILS", None)
    if not isinstance(stats, dict) or not stats:
        return

    coarse_aligned = manifest_context.get("aligned_supervised_rows")
    if coarse_aligned not in (None, ""):
        manifest_context["coarse_aligned_supervised_rows"] = int(coarse_aligned)

    manifest_context["alignment_attrition_stats"] = dict(stats)
    post_authority = stats.get("alignment_rows_post_authority_filter")
    if post_authority not in (None, ""):
        manifest_context["training_authority_aligned_rows"] = int(post_authority)

    if isinstance(details, dict) and details:
        manifest_context["alignment_attrition_details"] = dict(details)


__all__ = ["apply_training_alignment_attrition_to_manifest"]
