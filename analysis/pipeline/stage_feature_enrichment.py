"""Feature matrix enrichment stage helpers."""

from __future__ import annotations

import pandas as pd

from config import app_config
from utils import display_utils as du

from analysis.orchestration.permission_features import build_permission_feature_frame
from analysis.pipeline.sample_preparation import build_metadata_feature_frame


def build_permission_enrichment_frame(
    samples_df: pd.DataFrame,
    feature_flags: dict,
) -> pd.DataFrame | None:
    """Optionally build permission feature frame from permission observations."""
    enabled = bool(
        feature_flags.get(
            "enable_permission_features",
            getattr(app_config, "ENABLE_PERMISSION_FEATURES", True),
        )
    )
    if not enabled:
        return None

    min_support = int(getattr(app_config, "PERMISSION_MIN_SUPPORT", 2))
    max_features_cfg = getattr(app_config, "PERMISSION_MAX_FEATURES", 0)
    max_features = int(max_features_cfg) if int(max_features_cfg) > 0 else None
    permission_df = build_permission_feature_frame(
        samples_df=samples_df,
        min_permission_support=min_support,
        max_permission_features=max_features,
    )
    if permission_df.empty:
        return None
    du.print_info(
        "[FEATURES] Added permission feature frame: "
        f"{permission_df.shape[1] - 1} feature column(s)."
    )
    return permission_df


def merge_sample_metadata_features(
    extra_features_df: pd.DataFrame | None,
    samples_df: pd.DataFrame,
    feature_flags: dict,
    permission_features_df: pd.DataFrame | None = None,
) -> pd.DataFrame | None:
    """Optionally merge sample metadata-derived features.

    Args:
        extra_features_df: Existing enrichment frame.
        samples_df: Prepared sample cohort dataframe.
        feature_flags: Profile feature flag map.

    Returns:
        Merged enrichment dataframe or original value if feature is disabled.
    """
    enabled = bool(
        feature_flags.get(
            "enable_sample_metadata_features",
            getattr(app_config, "ENABLE_SAMPLE_METADATA_FEATURES", True),
        )
    )
    if not enabled:
        return extra_features_df

    metadata_features_df = build_metadata_feature_frame(samples_df)
    if metadata_features_df.empty:
        return extra_features_df

    merged = extra_features_df if isinstance(extra_features_df, pd.DataFrame) else None
    if isinstance(merged, pd.DataFrame) and not merged.empty:
        merged = merged.merge(metadata_features_df, on="sample_id", how="left")
    else:
        merged = metadata_features_df

    du.print_info(
        "[FEATURES] Added metadata feature frame: "
        f"{metadata_features_df.shape[1] - 1} feature column(s)."
    )

    if isinstance(permission_features_df, pd.DataFrame) and not permission_features_df.empty:
        merged = merged.merge(permission_features_df, on="sample_id", how="left")
        du.print_info(
            "[FEATURES] Fused permission features into enrichment frame: "
            f"{permission_features_df.shape[1] - 1} feature column(s)."
        )
    return merged
