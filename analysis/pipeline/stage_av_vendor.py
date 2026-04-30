"""Stage helpers for AV analysis, vendor extraction, and alignment."""

from __future__ import annotations

from typing import Any
from pathlib import Path

import pandas as pd

from analysis.pipeline import av_engine_pipeline, vendor_metadata_pipeline
from ml_classification.ml_utils import feature_label_alignment_helper
from config import app_config
from utils import display_utils as du
from utils.runtime_paths import resolve_diagnostics_dir


_REQUIRED_LABEL_COLUMNS = {"family_id", "family_canonical", "type_slug"}


def _diagnostics_dir_str() -> str:
    """Resolve diagnostics directory path for runtime context."""
    return str(resolve_diagnostics_dir())


def run_av_analysis_stage(
    samples_df: pd.DataFrame,
    run_id: str,
    profile_id: str,
    artifact_list: list[str],
) -> dict[str, Any] | None:
    """Run AV engine analysis and enforce lifecycle integrity checks.

    Args:
        samples_df: Prepared cohort dataframe.
        run_id: Active run identifier.
        profile_id: Active profile identifier.
        artifact_list: Mutable artifact list updated with emitted artifacts.

    Returns:
        Pipeline result dictionary if successful, otherwise ``None``.

    Raises:
        ValueError: If required outputs are missing or invalid.
    """
    av_config = {"run_id": run_id, "profile_context": profile_id}
    pipeline_results = av_engine_pipeline.run_av_analysis_pipeline(
        samples_df,
        config=av_config,
        verbose=True,
    )
    if not pipeline_results:
        du.print_error("[PIPELINE] AV analysis pipeline failed.")
        return None

    engine_scores_df = pipeline_results.get("engine_scores")
    if not isinstance(engine_scores_df, pd.DataFrame) or engine_scores_df.empty:
        raise ValueError("[INTEGRITY] Engine scoring produced no rows.")

    lifecycle_df = pipeline_results.get("engine_lifecycle")
    if isinstance(lifecycle_df, pd.DataFrame):
        artifact_list.append(str(Path(_diagnostics_dir_str()) / "engine_lifecycle.latest.csv"))
        _assert_engine_lifecycle_integrity(lifecycle_df)
        _assert_engine_count_consistency(
            lifecycle_df=lifecycle_df,
            engine_scores_df=engine_scores_df,
        )
        setattr(
            app_config,
            "RUNTIME_ENGINE_COUNT_INCLUDED_AFTER_GATING",
            int(engine_scores_df.attrs.get("engine_included_count", 0) or 0),
        )
        setattr(
            app_config,
            "RUNTIME_ENGINE_COUNT_EXCLUDED_AFTER_GATING",
            int(engine_scores_df.attrs.get("engine_excluded_count", 0) or 0),
        )

    return pipeline_results


def extract_vendor_metadata_stage(
    pipeline_results: dict[str, Any],
    samples_df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict, dict, pd.DataFrame] | tuple[None, None, None, None]:
    """Extract vendor metadata artifacts from AV pipeline output."""
    vendor_eval, vendor_records, parsed_data, scorecard_df = (
        vendor_metadata_pipeline.extract_vendor_metadata(pipeline_results, samples_df)
    )
    if any(item is None for item in [vendor_eval, parsed_data, scorecard_df]):
        du.print_error("[PIPELINE] Vendor metadata extraction failed.")
        return None, None, None, None
    return vendor_eval, vendor_records, parsed_data, scorecard_df


def run_feature_alignment_stage(
    feature_df: pd.DataFrame,
    samples_df: pd.DataFrame,
    diagnostics_dir: str,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Align feature matrix to required supervised labels."""
    missing_label_cols = sorted(_REQUIRED_LABEL_COLUMNS - set(samples_df.columns))
    if missing_label_cols:
        raise ValueError(
            f"[INTEGRITY] Missing required supervised label columns: {missing_label_cols}"
        )

    aligned_feature_df, aligned_labels_df = (
        feature_label_alignment_helper.perform_feature_label_alignment(
            feature_df=feature_df,
            label_df=samples_df,
            export_debug=True,
            output_dir=diagnostics_dir,
        )
    )
    if aligned_feature_df is None or aligned_labels_df is None:
        du.print_error("[PIPELINE] Feature-label alignment failed.")
        return None, None
    if len(aligned_feature_df) != len(aligned_labels_df):
        raise ValueError("[INTEGRITY] Corrupt feature matrix shape mismatch.")
    if hasattr(feature_df, "attrs") and hasattr(aligned_feature_df, "attrs"):
        aligned_feature_df.attrs.update(dict(feature_df.attrs))

    return aligned_feature_df, aligned_labels_df


def _assert_engine_lifecycle_integrity(lifecycle_df: pd.DataFrame) -> None:
    """Ensure lifecycle table includes at least one included engine."""
    def _bool_sum(column_name: str) -> int:
        if column_name not in lifecycle_df.columns:
            return 0
        return int(lifecycle_df[column_name].fillna(False).astype(bool).sum())

    observed_count = _bool_sum("observed_flag")
    canonicalized_count = _bool_sum("canonicalized_flag")
    included_count = _bool_sum("included_in_model_flag")
    excluded_count = int(len(lifecycle_df) - included_count)
    du.print_info(
        "[LIFECYCLE] Engines observed="
        f"{observed_count}, canonicalized={canonicalized_count}, "
        f"included={included_count}, excluded={excluded_count}"
    )
    if included_count == 0:
        raise ValueError("[INTEGRITY] included_engines == 0")


def _assert_engine_count_consistency(
    *,
    lifecycle_df: pd.DataFrame,
    engine_scores_df: pd.DataFrame,
) -> None:
    """Fail fast when lifecycle and attrs report mismatched included/excluded counts."""
    include_col = "included_in_model_flag"
    if include_col in lifecycle_df.columns:
        include_mask = lifecycle_df[include_col].fillna(False).astype(bool)
        lifecycle_included = int(include_mask.sum())
        lifecycle_excluded = int((~include_mask).sum())
    else:
        lifecycle_included = int(len(lifecycle_df))
        lifecycle_excluded = 0

    attr_included = int(engine_scores_df.attrs.get("engine_included_count", lifecycle_included) or 0)
    attr_excluded = int(engine_scores_df.attrs.get("engine_excluded_count", lifecycle_excluded) or 0)

    if lifecycle_included != attr_included or lifecycle_excluded != attr_excluded:
        raise ValueError(
            "[INTEGRITY] Engine lifecycle/attrs mismatch: "
            f"included lifecycle={lifecycle_included} attrs={attr_included}; "
            f"excluded lifecycle={lifecycle_excluded} attrs={attr_excluded}"
        )
