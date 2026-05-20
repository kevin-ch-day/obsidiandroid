"""Stage helpers for AV analysis, vendor extraction, and alignment.

Canonical implementation (**Pass 69**): ``obsidiandroid.pipeline.stage_av_vendor``;
``analysis.pipeline.stage_av_vendor`` is an identity shim.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path

import pandas as pd

from obsidiandroid.pipeline import av_engine_pipeline, vendor_metadata_pipeline
from obsidiandroid.modeling import feature_label_alignment_helper
from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.runtime_paths import resolve_diagnostics_dir
from obsidiandroid.observability.pipeline_observability.session import PipelineObservabilitySession
from obsidiandroid.observability.pipeline_observability.taxonomy import LogCategory, LogSeverity


_REQUIRED_LABEL_COLUMNS = {"family_id", "family_canonical", "type_slug"}


def _diagnostics_dir_str() -> str:
    """Resolve diagnostics directory path for runtime context."""
    return str(resolve_diagnostics_dir())


def _engine_lifecycle_path(run_id: str) -> Path:
    """Resolve canonical engine-lifecycle artifact path for the active run."""
    return oh.resolve_engine_lifecycle_path(Path(_diagnostics_dir_str()), run_id)


def run_av_analysis_stage(
    samples_df: pd.DataFrame,
    run_id: str,
    profile_id: str,
    artifact_list: list[str],
    manifest_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Run AV engine analysis and enforce lifecycle integrity checks.

    Args:
        samples_df: Prepared cohort dataframe.
        run_id: Active run identifier.
        profile_id: Active profile identifier.
        artifact_list: Mutable artifact list updated with emitted artifacts.
        manifest_context: Optional run dict holding ``pipeline_observability`` session.

    Returns:
        Pipeline result dictionary if successful, otherwise ``None``.

    Raises:
        ValueError: If required outputs are missing or invalid.
    """
    obs: PipelineObservabilitySession | None = None
    if isinstance(manifest_context, dict):
        maybe = manifest_context.get("pipeline_observability")
        if isinstance(maybe, PipelineObservabilitySession):
            obs = maybe

    av_config = {"run_id": run_id, "profile_context": profile_id}
    pipeline_results = av_engine_pipeline.run_av_analysis_pipeline(
        samples_df,
        config=av_config,
        verbose=True,
    )
    if not pipeline_results:
        du.print_error("[PIPELINE] AV analysis pipeline failed.")
        if obs is not None:
            obs.emit_artifact_skipped(
                reason="av_engine_pipeline_returned_falsy",
                path_hint="binary_matrix / engine_scores",
                detail="run_av_analysis_pipeline",
            )
        return None

    err_txt = pipeline_results.get("error")
    if err_txt:
        du.print_error(f"[PIPELINE] AV analysis halted: {err_txt}")
        if obs is not None:
            msg = str(err_txt)[:4000]
            obs.emit_jsonl(
                LogCategory.ERROR_RECOVERABLE,
                severity=LogSeverity.ERROR,
                message=msg,
                stage_hint="av_pipeline",
            )
        return None

    cohort_rows = int(len(samples_df))
    try:
        cohort_unique = (
            int(samples_df["sample_id"].nunique()) if "sample_id" in samples_df.columns else cohort_rows
        )
    except Exception:
        cohort_unique = cohort_rows
    bm = pipeline_results.get("binary_matrix")
    if obs is not None and isinstance(bm, pd.DataFrame) and not bm.empty:
        try:
            bm_rows = int(bm.index.nunique())
        except Exception:
            bm_rows = int(len(bm))
        obs.log_population_transition(
            transition="cohort_samples_to_binary_matrix_rows",
            previous_count=cohort_unique,
            new_count=bm_rows,
            reason="av_binary_matrix_builder (DB verdicts → melted rows → pivot)",
            artifact_path=str(_engine_lifecycle_path(run_id)),
        )

    engine_scores_df = pipeline_results.get("engine_scores")
    if not isinstance(engine_scores_df, pd.DataFrame) or engine_scores_df.empty:
        raise ValueError("[INTEGRITY] Engine scoring produced no rows.")

    lifecycle_df = pipeline_results.get("engine_lifecycle")
    lifecycle_path = _engine_lifecycle_path(run_id)
    if isinstance(lifecycle_df, pd.DataFrame):
        artifact_list.append(str(lifecycle_path))
        if obs is not None:
            obs.emit_artifact_written(str(lifecycle_path), detail="engine lifecycle CSV")
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
    elif obs is not None:
        obs.emit_artifact_skipped(
            reason="engine_lifecycle_not_attached_as_dataframe",
            path_hint=str(lifecycle_path),
            detail="check score_av_engines lifecycle export",
        )

    return pipeline_results


def extract_vendor_metadata_stage(
    pipeline_results: dict[str, Any],
    samples_df: pd.DataFrame,
    manifest_context: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict, dict, pd.DataFrame] | tuple[None, None, None, None]:
    """Extract vendor metadata artifacts from AV pipeline output."""
    vendor_eval, vendor_records, parsed_data, scorecard_df = (
        vendor_metadata_pipeline.extract_vendor_metadata(pipeline_results, samples_df)
    )
    if any(item is None for item in [vendor_eval, parsed_data, scorecard_df]):
        du.print_error("[PIPELINE] Vendor metadata extraction failed.")
        obs: PipelineObservabilitySession | None = None
        if isinstance(manifest_context, dict):
            maybe_vm = manifest_context.get("pipeline_observability")
            if isinstance(maybe_vm, PipelineObservabilitySession):
                obs = maybe_vm
        if obs is not None:
            obs.emit_artifact_skipped(
                reason="vendor_metadata_extraction_partial_or_null_components",
                path_hint=str(Path(_diagnostics_dir_str()) / "vendor_eval*.csv"),
                detail=(
                    "vendor_eval "
                    + str(vendor_eval is None)
                    + " parsed_data "
                    + str(parsed_data is None)
                    + " scorecard_df "
                    + str(scorecard_df is None)
                ),
            )
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
