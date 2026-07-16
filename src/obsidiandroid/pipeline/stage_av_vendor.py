"""Stage helpers for AV analysis, vendor extraction, and alignment.

Canonical implementation (**Pass 69**): ``obsidiandroid.pipeline.stage_av_vendor``;
The supported import path is ``obsidiandroid.pipeline.stage_av_vendor``.
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
from obsidiandroid.common import output_paths
from obsidiandroid.common.runtime_paths import resolve_diagnostics_dir
from obsidiandroid.pipeline.engine_normalization import canonicalize_engine_name
from obsidiandroid.pipeline.engine_lifecycle_schema import readiness_mask
from obsidiandroid.observability.pipeline_observability.session import PipelineObservabilitySession
from obsidiandroid.observability.pipeline_observability.taxonomy import LogCategory, LogSeverity


_REQUIRED_LABEL_COLUMNS = {"family_id", "family_canonical", "type_slug"}


def _diagnostics_dir_str() -> str:
    """Resolve diagnostics directory path for runtime context."""
    return str(resolve_diagnostics_dir())


def _engine_lifecycle_path(run_id: str) -> Path:
    """Resolve canonical engine-lifecycle artifact path for the active run."""
    runtime_dir = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    normalized_run_id = oh.normalize_artifact_run_id(run_id)
    if runtime_dir:
        return Path(runtime_dir) / f"engine_lifecycle_{normalized_run_id}.csv"
    return output_paths.diagnostics_root() / f"engine_lifecycle_{normalized_run_id}.csv"


def _av_feature_scope_contract_path(run_id: str) -> Path:
    """Return the run-scoped AV binary-feature scope contract path."""
    runtime_dir = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    normalized_run_id = oh.normalize_artifact_run_id(run_id)
    if runtime_dir:
        return Path(runtime_dir) / f"av_binary_feature_scope_{normalized_run_id}.csv"
    return output_paths.diagnostics_root() / f"av_binary_feature_scope_{normalized_run_id}.csv"


def _export_av_feature_scope_contract(
    *,
    lifecycle_df: pd.DataFrame,
    binary_matrix: pd.DataFrame | None,
    scope_contract: dict[str, Any] | None,
    run_id: str,
    profile_id: str,
) -> str:
    """Export lifecycle status beside actual binary-feature membership.

    Engine readiness and binary feature membership are separate surfaces.  This
    compact, run-scoped table makes their relationship explicit without
    claiming that a parser score controls every AV verdict column.
    """
    if not isinstance(lifecycle_df, pd.DataFrame) or lifecycle_df.empty:
        return ""
    frame = lifecycle_df.copy()
    source_columns = []
    if isinstance(binary_matrix, pd.DataFrame) and "sample_id" in binary_matrix.columns:
        source_columns = [str(col) for col in binary_matrix.columns if str(col) != "sample_id"]
    source_canonical = {canonicalize_engine_name(column) for column in source_columns}
    canonical_col = "engine_name_canonical"
    if canonical_col not in frame.columns:
        return ""
    frame["binary_matrix_column_present"] = frame[canonical_col].map(
        lambda value: int(canonicalize_engine_name(value) in source_canonical)
    )
    resolved = dict(scope_contract or {})
    frame["binary_feature_engine_scope"] = str(
        resolved.get("binary_feature_engine_scope", "all_observed")
    )
    frame["selected_for_binary_feature_scope"] = frame["binary_matrix_column_present"]
    frame["observed_binary_engine_columns"] = int(
        resolved.get("observed_binary_engine_columns", len(source_columns)) or 0
    )
    frame["selected_binary_engine_columns"] = int(
        resolved.get("selected_binary_engine_columns", len(source_columns)) or 0
    )
    frame["run_id"] = str(run_id)
    frame["profile_id"] = str(profile_id)

    path = _av_feature_scope_contract_path(run_id)
    paths = oh.mirror_csv_text_run_then_global(
        diagnostics_dir=path.parent,
        run_filename=path.name,
        csv_text=frame.to_csv(index=False),
        global_latest_name="av_binary_feature_scope.latest.csv",
    )
    return str(paths[0])


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

    # Pass the scope explicitly as part of the stage contract rather than
    # relying only on process-global configuration.  This is recorded again in
    # the run artifacts and makes a paired AV-scope experiment auditable.
    av_config = {
        "run_id": run_id,
        "profile_context": profile_id,
        "binary_feature_engine_scope": str(
            getattr(app_config, "AV_BINARY_FEATURE_ENGINE_SCOPE", "all_observed")
        ),
    }
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
        exclusion_audit_path = str(engine_scores_df.attrs.get("engine_exclusion_audit_path", "") or "").strip()
        if exclusion_audit_path:
            artifact_list.append(exclusion_audit_path)
            if obs is not None:
                obs.emit_artifact_written(exclusion_audit_path, detail="engine exclusion audit CSV")
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
            "RUNTIME_ENGINE_COUNT_OBSERVED",
            int(engine_scores_df.attrs.get("engine_observed_count", 0) or 0),
        )
        setattr(
            app_config,
            "RUNTIME_ENGINE_COUNT_CANONICAL",
            int(engine_scores_df.attrs.get("engine_canonical_count", 0) or 0),
        )
        setattr(
            app_config,
            "RUNTIME_ENGINE_COUNT_NEAR_MISS",
            int(engine_scores_df.attrs.get("engine_near_miss_count", 0) or 0),
        )
        setattr(
            app_config,
            "RUNTIME_ENGINE_COUNT_EXCLUDED_AFTER_GATING",
            int(engine_scores_df.attrs.get("engine_excluded_count", 0) or 0),
        )
        feature_scope_contract = pipeline_results.get("av_binary_feature_scope_contract")
        if not isinstance(feature_scope_contract, dict):
            feature_scope_contract = {}
        scope_name = str(
            feature_scope_contract.get(
                "binary_feature_engine_scope",
                getattr(app_config, "AV_BINARY_FEATURE_ENGINE_SCOPE", "all_observed"),
            )
        )
        selected_binary_count = int(
            feature_scope_contract.get("selected_binary_engine_columns", 0) or 0
        )
        observed_binary_count = int(
            feature_scope_contract.get("observed_binary_engine_columns", 0) or 0
        )
        setattr(app_config, "RUNTIME_AV_BINARY_FEATURE_ENGINE_SCOPE", scope_name)
        setattr(app_config, "RUNTIME_AV_BINARY_FEATURE_ENGINE_COUNT", selected_binary_count)
        scope_path = _export_av_feature_scope_contract(
            lifecycle_df=lifecycle_df,
            binary_matrix=bm if isinstance(bm, pd.DataFrame) else None,
            scope_contract=feature_scope_contract,
            run_id=run_id,
            profile_id=profile_id,
        )
        if scope_path:
            setattr(app_config, "RUNTIME_AV_FEATURE_SCOPE_CONTRACT_CSV", scope_path)
            artifact_list.append(scope_path)
            if obs is not None:
                obs.emit_artifact_written(scope_path, detail="AV binary-feature scope contract CSV")
        du.print_stat(
            "AV Feature Contract",
            (
                f"scope={scope_name}, binary_engine_columns="
                f"{selected_binary_count}/{observed_binary_count}"
            ),
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
    included_count = int(readiness_mask(lifecycle_df).sum())
    excluded_count = int(len(lifecycle_df) - included_count)
    du.print_stat(
        "Engine Lifecycle",
        (
            f"observed={observed_count}, canonicalized={canonicalized_count}, "
            f"included={included_count}, excluded={excluded_count}"
        ),
    )
    if included_count == 0:
        raise ValueError("[INTEGRITY] included_engines == 0")


def _assert_engine_count_consistency(
    *,
    lifecycle_df: pd.DataFrame,
    engine_scores_df: pd.DataFrame,
) -> None:
    """Fail fast when lifecycle and attrs report mismatched included/excluded counts."""
    if {"readiness_eligible_flag", "included_in_model_flag"}.intersection(lifecycle_df.columns):
        include_mask = readiness_mask(lifecycle_df)
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
