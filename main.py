# Filename: main.py
# Purpose  : Executes the end-to-end malware classification pipeline

"""Entry point for the malware classification pipeline."""

import os
import sys
import traceback
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Sequence, Any
from time import perf_counter

import pandas as pd

from config import app_config

# === Database + Utilities ===
from utils import display_utils as du
from utils import ml_console
from utils import family_distribution_report
from utils import profile_manager
from utils import run_manifest
from utils import evidence_mode_resolver
from utils.logging import runtime as runtime_logging
from utils.logging import logger as logger_manager
from utils import output_paths
from utils.logging import get_logger, log_event
from utils.hash_utils import hash_payload
from analysis.pipeline.governance.integrity import enforce_run_scoped_artifact_paths

# === Analysis Pipelines (staged pipeline) ===
from analysis.pipeline.stage_av_vendor import (
    extract_vendor_metadata_stage,
    run_av_analysis_stage,
    run_feature_alignment_stage,
)
from analysis.pipeline.stage_samples import load_and_prepare_samples
from analysis.pipeline.stage_feature_enrichment import merge_sample_metadata_features
from analysis.pipeline.stage_feature_enrichment import build_permission_enrichment_frame
from analysis.pipeline.stage_ablation import run_ablation_experiments
from analysis.pipeline.stage_permission_trends_report import run_permission_trends_report_stage
from analysis.pipeline.stage_modeling import (
    build_feature_matrix_stage,
    compute_engine_weights_from_pipeline,
    resolve_final_labels_stage,
    run_training_stage,
)
from analysis.pipeline.stage_manifest import finalize_run_manifest_stage
from analysis.pipeline.runtime_policy import (
    apply_profile_runtime_policy,
    build_mutable_config_keys,
    enforce_paper_perturbation_axes as enforce_paper_perturbation_axes_policy,
    reset_runtime_markers,
)
from analysis.orchestration.methodology_artifacts import (
    export_feature_contract,
    export_leakage_assessment,
    export_modality_method_contract,
)
from analysis.orchestration.metadata_features import (
    build_metadata_feature_frame,
    extract_vt_tag_count,
)
from analysis.orchestration.profile_filters import (
    apply_dataset_filters,
    split_benign_malicious,
    summarize_dataset_partitions,
    export_cohort_filter_summary,
)
from analysis.orchestration.runtime_reporting import (
    apply_confusion_matrix_policy as _apply_confusion_matrix_policy,
    build_run_summary_payload as _build_run_summary_payload,
    collect_dependency_versions as _collect_dependency_versions,
    enforce_duplicate_sha_policy as _enforce_duplicate_sha_policy,
    export_aligned_training_cache as _export_aligned_training_cache,
    export_and_print_run_summary as _export_and_print_run_summary,
    export_model_config_snapshot as _export_model_config_snapshot,
    extract_model_summary as _extract_model_summary,
    parse_key_value_meta as _parse_key_value_meta,
    print_run_context_line as _print_run_context_line,
    setup_runtime_context,
)
from database.db_sample_metadata_contracts import get_query_contract_metadata

# Default diagnostics path derived from app configuration
DIAGNOSTICS_DIR = os.path.join(app_config.DEFAULT_OUTPUT_DIR, "diagnostics")
COHORT_FILTER_SUMMARY_PATH = Path(DIAGNOSTICS_DIR) / "analysis_snapshot_filter_summary.latest.csv"
# Keep legacy module constant for backward compatibility; use runtime-resolved
# path inside run_pipeline for paper-mode routing.
PARSER_QUALITY_PATH = Path(DIAGNOSTICS_DIR) / "parser_quality.latest.csv"
PIPELINE_MAIN_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.pipeline.main",
    "pipeline",
)
_CONFIG_MISSING = object()


class _ScopedArtifactList(list[str]):
    """Artifact list with immediate run-scope path enforcement on append/extend."""

    def __init__(
        self,
        *,
        strict_run_scoped: bool,
        run_root_getter,
        output_root_getter,
        allow_global_getter,
    ) -> None:
        super().__init__()
        self._strict = bool(strict_run_scoped)
        self._run_root_getter = run_root_getter
        self._output_root_getter = output_root_getter
        self._allow_global_getter = allow_global_getter

    def _validate(self, item: str) -> None:
        if not self._strict:
            return
        if bool(self._allow_global_getter()):
            return
        path_text = str(item).strip()
        if not path_text:
            return
        enforce_run_scoped_artifact_paths(
            artifact_paths=[path_text],
            run_root=Path(str(self._run_root_getter())),
            output_root=Path(str(self._output_root_getter())),
            allow_latest=True,
        )

    def append(self, item: str) -> None:  # type: ignore[override]
        self._validate(str(item))
        super().append(str(item))

    def extend(self, items) -> None:  # type: ignore[override]
        for item in items:
            self.append(str(item))


class _PipelineStageFailure(RuntimeError):
    """Expected pipeline-stage failure that should finalize cleanly."""

# -------------------------------------------------------------------
# Backward-compatible wrappers (retain these so older imports/tests survive)
# -------------------------------------------------------------------

def compute_engine_weights(pipeline_results: dict) -> Optional[pd.DataFrame]:
    """Backward-compatible wrapper for engine weight computation stage."""
    return compute_engine_weights_from_pipeline(pipeline_results)


def generate_feature_matrix(
    weights_df: pd.DataFrame,
    vendor_data: dict,
    extra_features: pd.DataFrame | None = None,
) -> Optional[pd.DataFrame]:
    """Backward-compatible wrapper for feature matrix stage."""
    try:
        return build_feature_matrix_stage(weights_df, vendor_data, extra_features)
    except Exception as e:
        du.print_error(f"[ERROR] Feature matrix generation failed: {e}")
        return None


def resolve_final_labels(vendor_records: dict, model_output: dict) -> Optional[pd.DataFrame]:
    """Backward-compatible wrapper for final label resolution stage."""
    return resolve_final_labels_stage(vendor_records, model_output)


def _extract_vt_tag_count(value: object) -> int:
    """Backward-compatible wrapper for VT tag count parsing."""
    return extract_vt_tag_count(value)


def _build_metadata_feature_frame(samples_df: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible wrapper for metadata feature construction."""
    return build_metadata_feature_frame(samples_df)


def _split_benign_malicious(samples_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Backward-compatible wrapper for profile partition splitting."""
    return split_benign_malicious(samples_df)


def _summarize_dataset_partitions(
    source_df: pd.DataFrame,
    output_df: pd.DataFrame,
    benign_df: pd.DataFrame,
    malicious_df: pd.DataFrame,
    mode: str,
    benign_ratio_target: float | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper for partition diagnostics."""
    return summarize_dataset_partitions(
        source_df=source_df,
        output_df=output_df,
        benign_df=benign_df,
        malicious_df=malicious_df,
        mode=mode,
        benign_ratio_target=benign_ratio_target,
    )


def _export_cohort_filter_summary(summary: dict[str, Any], run_id: str, profile_id: str) -> str:
    """Backward-compatible wrapper for analysis snapshot filter summary export."""
    return export_cohort_filter_summary(
        summary=summary,
        run_id=run_id,
        profile_id=profile_id,
        output_path=COHORT_FILTER_SUMMARY_PATH,
    )


def _apply_dataset_filters(samples_df: pd.DataFrame, profile: dict[str, Any]) -> pd.DataFrame:
    """Backward-compatible wrapper for dataset profile filtering."""
    return apply_dataset_filters(samples_df=samples_df, profile=profile)


# -------------------------------------------------------------------
# Pipeline
# -------------------------------------------------------------------

def run_pipeline(
    selected_models: Optional[Sequence[str]] = None,
    stop_after: str = "full",
    profile_ref: Optional[str] = None,
    evidence_mode_override: Optional[bool] = None,
    paper_mode_override: Optional[bool] = None,
    allow_evidence_override: bool = False,
    allow_global_artifacts: bool = False,
) -> int:
    """Execute the malware classification workflow with optional stage/model controls.

    Args:
        selected_models: Optional list of model keys to train (for targeted runs).
        stop_after: Optional pipeline cutoff stage. Supported values:
            "full", "samples", "av_pipeline", "vendor_metadata",
            "engine_weights", "feature_matrix", "alignment", "training",
            "ablation", "permission_trends", "label_resolution".
        profile_ref: Required profile id/path from `profiles/`.
    """
    global DIAGNOSTICS_DIR

    valid_stages = {
        "full",
        "samples",
        "av_pipeline",
        "vendor_metadata",
        "engine_weights",
        "feature_matrix",
        "alignment",
        "training",
        "ablation",
        "permission_trends",
        "label_resolution",
    }
    if stop_after not in valid_stages:
        du.print_warning(f"[PIPELINE] Unknown stop_after='{stop_after}'. Falling back to 'full'.")
        stop_after = "full"

    if not profile_ref:
        du.print_error("[PROFILE] No profile provided. Use startup menu profile selection.")
        return 1

    model_list = list(selected_models) if selected_models else None
    profile: dict[str, Any] = {}
    run_id = run_manifest.generate_run_id()
    # Snapshot mutable config before setup_runtime_context mutates run-scoped paths
    # (RUNTIME_DIAGNOSTICS_DIR, ANALYSIS_SNAPSHOT_*, etc.); otherwise finally restores
    # stale run directories and leaks state across tests or sequential CLI runs.
    mutable_config_keys = build_mutable_config_keys()
    mutable_config_snapshot: dict[str, Any] = {
        key: getattr(app_config, key, _CONFIG_MISSING) for key in mutable_config_keys
    }
    setattr(app_config, "RUNTIME_RUN_ID", run_id)
    strict_run_scoped = True
    runtime_paths = setup_runtime_context(run_id=run_id, strict_run_scoped=True)
    output_root_base = runtime_paths["output_root_base"]
    runtime_run_root = runtime_paths["runtime_run_root"]
    DIAGNOSTICS_DIR = str(runtime_paths["runtime_diagnostics_dir"])
    artifact_list: _ScopedArtifactList = _ScopedArtifactList(
        strict_run_scoped=strict_run_scoped,
        run_root_getter=lambda: getattr(app_config, "RUNTIME_RUN_ROOT", runtime_run_root),
        output_root_getter=lambda: output_root_base,
        allow_global_getter=lambda: bool(getattr(app_config, "RUNTIME_ALLOW_GLOBAL_ARTIFACTS", False)),
    )
    samples_df: pd.DataFrame | None = None
    pipeline_results: dict[str, Any] = {}
    vendor_eval: pd.DataFrame | None = None
    manifest_context: dict[str, Any] = {
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "stop_after": stop_after,
    }
    runtime_log_context = None
    pipeline_started_at = perf_counter()
    stage_timings_sec: dict[str, float] = {}
    current_stage_name: str | None = None
    last_completed_stage: str | None = None
    preflight_path: Path | None = None
    preflight_payload: dict[str, Any] = {}
    original_diagnostics_dir = DIAGNOSTICS_DIR
    # Reset run-scoped runtime markers up-front to avoid stale cross-run leakage.
    reset_runtime_markers()

    def _record_stage_timing(stage_name: str, started_at: float) -> None:
        nonlocal last_completed_stage
        duration = max(0.0, perf_counter() - started_at)
        stage_timings_sec[stage_name] = duration
        last_completed_stage = stage_name
        manifest_context["completed_stage"] = stage_name
        du.print_info(f"[TIME] {stage_name}: {duration:.2f}s")
        log_event(
            PIPELINE_MAIN_LOGGER,
            "stage_timing",
            run_id=run_id,
            stage=stage_name,
            duration_sec=round(duration, 2),
        )

    def _mark_run_state(
        status: str,
        *,
        completed_stage: str | None = None,
        failure_reason: str = "",
        failed_stage: str | None = None,
    ) -> None:
        """Persist concise run-state metadata for final summary and manifest export."""
        normalized_status = str(status).strip().lower() or "unknown"
        manifest_context["run_status"] = normalized_status
        resolved_completed_stage = completed_stage or last_completed_stage or ""
        if resolved_completed_stage:
            manifest_context["completed_stage"] = resolved_completed_stage
        if failure_reason:
            manifest_context["failure_reason"] = failure_reason
            resolved_failed_stage = failed_stage or current_stage_name or resolved_completed_stage
            if resolved_failed_stage:
                manifest_context["failed_stage"] = resolved_failed_stage
        else:
            manifest_context.pop("failure_reason", None)
            manifest_context.pop("failed_stage", None)

    def _begin_stage(stage_name: str) -> None:
        """Track the active stage for failure reporting."""
        nonlocal current_stage_name
        current_stage_name = stage_name
        manifest_context["current_stage"] = stage_name

    def _attach_runtime_timing_context() -> None:
        total_runtime = max(0.0, perf_counter() - pipeline_started_at)
        manifest_context["stage_timings_sec"] = {
            k: round(v, 3) for k, v in stage_timings_sec.items()
        }
        manifest_context["pipeline_runtime_sec"] = round(total_runtime, 3)
        if last_completed_stage and "completed_stage" not in manifest_context:
            manifest_context["completed_stage"] = last_completed_stage
        if stage_timings_sec:
            timings_path = Path(DIAGNOSTICS_DIR) / "pipeline_stage_timings.latest.csv"
            timings_path.parent.mkdir(parents=True, exist_ok=True)
            timings_df = pd.DataFrame(
                [
                    {"stage": stage, "duration_sec": round(duration, 3)}
                    for stage, duration in stage_timings_sec.items()
                ]
            )
            timings_df["run_id"] = run_id
            timings_df["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
            timings_df.to_csv(timings_path, index=False)
            if str(timings_path) not in artifact_list:
                artifact_list.append(str(timings_path))

    def _finalize_with_manifest_timing() -> int:
        """Finalize run manifest and record manifest stage timing."""
        stage_started = perf_counter()
        _attach_runtime_timing_context()
        result = _finalize_run_manifest(
            manifest_context=manifest_context,
            profile=profile,
            samples_df=samples_df,
            pipeline_results=pipeline_results,
            vendor_eval_df=vendor_eval,
            artifact_list=artifact_list,
        )
        _record_stage_timing("manifest", stage_started)
        _attach_runtime_timing_context()
        return result

    def _write_preflight(status: str, reason: str = "") -> None:
        """Write evidence-mode preflight report for auditability."""
        nonlocal preflight_path, preflight_payload
        if not bool(
            getattr(
                app_config,
                "EVIDENCE_MODE_ENABLED",
                getattr(app_config, "PAPER_MODE_ENABLED", False),
            )
        ):
            return
        run_root = Path(str(getattr(app_config, "RUNTIME_RUN_ROOT", app_config.DEFAULT_OUTPUT_DIR)))
        diagnostics_dir = run_root / "diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        if preflight_path is None:
            preflight_path = diagnostics_dir / "preflight_report.json"
        preflight_payload.update(
            {
                "run_id": run_id,
                "status": status,
                "reason": reason,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "config_hash": manifest_context.get("config_hash", ""),
                "evidence_mode": manifest_context.get("evidence_mode", {}),
            }
        )
        preflight_path.write_text(
            json.dumps(preflight_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        if str(preflight_path) not in artifact_list:
            artifact_list.append(str(preflight_path))

    def _fail_pipeline(reason: str, *, stage_name: str | None = None) -> None:
        """Route expected stage failures through the shared finalization path."""
        if stage_name:
            _begin_stage(stage_name)
        _mark_run_state(
            "failed",
            failure_reason=reason,
            failed_stage=stage_name or current_stage_name,
        )
        _write_preflight(status="failed", reason=reason)
        raise _PipelineStageFailure(reason)

    try:
        du.print_banner("Malware Classification Framework")
        du.print_stat("Run ID", run_id)
        if runtime_log_context is not None:
            du.print_info(f"[LOG] Runtime stream log: {runtime_log_context.log_path}")

        # Ensure diagnostics directory exists
        os.makedirs(DIAGNOSTICS_DIR, exist_ok=True)

        # Load profile
        profile = profile_manager.load_profile(profile_ref)
        requested_evidence_mode = (
            evidence_mode_override if evidence_mode_override is not None else paper_mode_override
        )
        env_evidence_value = os.environ.get(
            evidence_mode_resolver.ENV_EVIDENCE_MODE,
            os.environ.get(evidence_mode_resolver.ENV_LEGACY_PAPER_MODE),
        )
        preliminary_resolution = evidence_mode_resolver.resolve_evidence_mode(
            cli_value=requested_evidence_mode,
            env_value=env_evidence_value,
            profile=profile,
            default=True,
            strict_env=False,
        )
        strict_env = bool(preliminary_resolution.resolved_value)
        evidence_resolution = evidence_mode_resolver.resolve_evidence_mode(
            cli_value=requested_evidence_mode,
            env_value=env_evidence_value,
            profile=profile,
            default=True,
            strict_env=strict_env,
        )
        locked_value = getattr(
            app_config,
            "EVIDENCE_MODE_LOCKED_VALUE",
            getattr(app_config, "PAPER_MODE_LOCKED_VALUE", None),
        )
        effective_evidence_mode = evidence_mode_resolver.enforce_immutable_lock(
            locked_value=locked_value if isinstance(locked_value, bool) else None,
            requested_value=bool(evidence_resolution.resolved_value),
        )
        evidence_mode_source = evidence_resolution.source
        declared_axes = (
            profile.get("evidence_perturbation_axes", profile.get("paper_perturbation_axes", []))
            if isinstance(profile, dict)
            else []
        )
        if (
            effective_evidence_mode
            and evidence_resolution.source == "default"
            and (not isinstance(declared_axes, list) or not declared_axes)
        ):
            # Keep default behavior safe for profiles that are not strict-evidence aware.
            effective_evidence_mode = False
            evidence_mode_source = "default_profile_ineligible"
        setattr(app_config, "EVIDENCE_MODE_ENABLED", effective_evidence_mode)
        setattr(app_config, "EVIDENCE_MODE_LOCKED_VALUE", effective_evidence_mode)
        setattr(app_config, "PAPER_MODE_ENABLED", effective_evidence_mode)
        setattr(app_config, "PAPER_MODE_LOCKED_VALUE", effective_evidence_mode)
        manifest_context["evidence_mode"] = {
            "resolved_value": bool(effective_evidence_mode),
            "source": evidence_mode_source,
            "raw_inputs": evidence_resolution.raw_inputs,
        }
        manifest_context["paper_mode"] = dict(manifest_context["evidence_mode"])
        if effective_evidence_mode:
            run_root = output_root_base / "runs" / run_id
            run_root.mkdir(parents=True, exist_ok=True)
            setattr(app_config, "RUNTIME_RUN_ROOT", str(run_root))
            setattr(app_config, "DEFAULT_OUTPUT_DIR", str(run_root))
            DIAGNOSTICS_DIR = str(run_root / "diagnostics")
            setattr(app_config, "ANALYSIS_SNAPSHOT_FILE", str(Path(DIAGNOSTICS_DIR) / "analysis_snapshot.latest.csv"))
            setattr(
                app_config,
                "ANALYSIS_SNAPSHOT_META_FILE",
                str(Path(DIAGNOSTICS_DIR) / "analysis_snapshot.latest.meta.txt"),
            )
            setattr(
                app_config,
                "ANALYSIS_SNAPSHOT_CONFLICT_FILE",
                str(Path(DIAGNOSTICS_DIR) / "analysis_snapshot_label_conflicts.latest.csv"),
            )
            setattr(
                app_config,
                "PAPER_COHORT_SAMPLE_IDS_FILE",
                str(Path(DIAGNOSTICS_DIR) / "paper_cohort_sample_ids.csv"),
            )
            setattr(
                app_config,
                "DATASET_TIME_CONTRACT_FILE",
                str(Path(DIAGNOSTICS_DIR) / "dataset_time_contract.latest.json"),
            )
            setattr(
                app_config,
                "ALIGNED_FEATURE_CACHE_FILE",
                str(Path(DIAGNOSTICS_DIR) / "aligned_features.latest.csv.gz"),
            )
            setattr(
                app_config,
                "ALIGNED_LABEL_CACHE_FILE",
                str(Path(DIAGNOSTICS_DIR) / "aligned_labels.latest.csv"),
            )
            du.print_info(f"[EVIDENCE] Run root: {run_root}")
        enforce_paper_perturbation_axes_policy(profile=profile, paper_mode=effective_evidence_mode)
        runtime_log_context = runtime_logging.start_runtime_logging(run_id)
        if runtime_log_context is not None:
            artifact_list.append(str(runtime_log_context.log_path))
        manifest_context["profile_params"] = profile
        manifest_context["config_hash"] = hash_payload(profile)
        manifest_context["dependency_versions"] = _collect_dependency_versions()
        manifest_context["db_query_contract"] = get_query_contract_metadata()
        _write_preflight(status="running")
        du.print_info(f"[PROFILE] Loaded profile: {profile.get('profile_id')}")
        du.print_info(
            f"[EVIDENCE] Mode={'ON' if effective_evidence_mode else 'OFF'} "
            f"(source={evidence_resolution.source})"
        )

        feature_flags = profile.get("feature_flags", {}) if isinstance(profile, dict) else {}
        policy = apply_profile_runtime_policy(
            profile=profile,
            feature_flags=feature_flags,
            allow_evidence_override=allow_evidence_override,
            allow_global_artifacts=allow_global_artifacts,
            manifest_context=manifest_context,
        )
        type_slug = policy["type_slug"]
        profile_id = str(policy["profile_id"])
        if bool(getattr(app_config, "EVIDENCE_MODE_ENABLED", getattr(app_config, "PAPER_MODE_ENABLED", False))) and bool(
            getattr(app_config, "ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS", True)
        ):
            _fail_pipeline(
                "[EVIDENCE] Dynamic generic vendor onboarding must be disabled in evidence mode.",
                stage_name="preflight",
            )

        # Step 1: Load and prepare sample metadata
        stage_started_at = perf_counter()
        _begin_stage("samples")
        _print_run_context_line(
            run_id=run_id,
            profile_id=profile_id,
            stage="samples",
            stop_after=stop_after,
            selected_models=model_list,
        )
        samples_df = load_and_prepare_samples(
            profile=profile,
            profile_id=profile_id,
            type_slug=type_slug,
            run_id=run_id,
            artifact_list=artifact_list,
        )
        snapshot_file = Path(
            getattr(
                app_config,
                "ANALYSIS_SNAPSHOT_FILE",
                getattr(app_config, "COHORT_SNAPSHOT_FILE", ""),
            )
        )
        snapshot_meta_file = Path(
            getattr(
                app_config,
                "ANALYSIS_SNAPSHOT_META_FILE",
                getattr(app_config, "COHORT_SNAPSHOT_META_FILE", ""),
            )
        )
        snapshot_meta = _parse_key_value_meta(snapshot_meta_file)
        manifest_context["analysis_snapshot"] = {
            "snapshot_file": str(snapshot_file),
            "meta_file": str(snapshot_meta_file),
            "selection_rule_version": str(
                snapshot_meta.get(
                    "selection_rule_version",
                    getattr(app_config, "ANALYSIS_SELECTION_RULE_VERSION", "snapshot_v1"),
                )
            ),
            "snapshot_row_count": int(snapshot_meta.get("sample_count", len(samples_df))),
            "snapshot_sha256_hash": str(snapshot_meta.get("snapshot_sha256_hash", "")),
            "snapshot_sample_id_hash": str(snapshot_meta.get("sample_id_sha256", "")),
            "snapshot_label_conflict_count": int(snapshot_meta.get("label_conflict_count", "0")),
        }
        gate_rows = samples_df.attrs.get("cohort_gate_rows", [])
        unknown_excluded = 0
        if isinstance(gate_rows, list):
            for row in gate_rows:
                if not isinstance(row, dict):
                    continue
                if str(row.get("gate_name", "")) == "exclude_unknown_family_canonical":
                    unknown_excluded += int(row.get("dropped", 0) or 0)
        manifest_context["unknown_excluded_count"] = int(unknown_excluded)
        manifest_context["dataset_time_contract_path"] = str(
            getattr(app_config, "DATASET_TIME_CONTRACT_FILE", "")
        )
        _record_stage_timing("samples", stage_started_at)
        if samples_df is None or samples_df.empty:
            raise ValueError("No samples found after preparation.")

        if stop_after == "samples":
            _mark_run_state("partial", completed_stage="samples")
            du.print_success("[PIPELINE] Stopped after sample preparation by request.")
            pipeline_results = None
            vendor_eval = None
            return _finalize_with_manifest_timing()

        # Step 2: Run AV engine pipeline
        stage_started_at = perf_counter()
        _begin_stage("av_pipeline")
        _print_run_context_line(
            run_id=run_id,
            profile_id=profile_id,
            stage="av_pipeline",
            stop_after=stop_after,
            selected_models=model_list,
        )
        pipeline_results = run_av_analysis_stage(
            samples_df=samples_df,
            run_id=run_id,
            profile_id=profile_id,
            artifact_list=artifact_list,
        )
        _record_stage_timing("av_pipeline", stage_started_at)
        if not pipeline_results:
            _fail_pipeline("[PIPELINE] AV pipeline returned no results.")

        if stop_after == "av_pipeline":
            _mark_run_state("partial", completed_stage="av_pipeline")
            du.print_success("[PIPELINE] Stopped after AV pipeline by request.")
            vendor_eval = None
            return _finalize_with_manifest_timing()

        # Step 3: Extract vendor metadata
        stage_started_at = perf_counter()
        _begin_stage("vendor_metadata")
        _print_run_context_line(
            run_id=run_id,
            profile_id=profile_id,
            stage="vendor_metadata",
            stop_after=stop_after,
            selected_models=model_list,
        )
        vendor_eval, vendor_records, parsed_data, scorecard_df = extract_vendor_metadata_stage(
            pipeline_results=pipeline_results,
            samples_df=samples_df,
        )
        _record_stage_timing("vendor_metadata", stage_started_at)
        if vendor_eval is None:
            _fail_pipeline("[PIPELINE] Vendor metadata extraction returned no evaluation frame.")

        pipeline_results["vendor_eval_df"] = vendor_eval
        parser_quality_path = Path(DIAGNOSTICS_DIR) / "parser_quality.latest.csv"
        if parser_quality_path.exists():
            artifact_list.append(str(parser_quality_path))

        if stop_after == "vendor_metadata":
            _mark_run_state("partial", completed_stage="vendor_metadata")
            du.print_success("[PIPELINE] Stopped after vendor metadata by request.")
            return _finalize_with_manifest_timing()

        # Step 4: Compute engine weights
        stage_started_at = perf_counter()
        _begin_stage("engine_weights")
        _print_run_context_line(
            run_id=run_id,
            profile_id=profile_id,
            stage="engine_weights",
            stop_after=stop_after,
            selected_models=model_list,
        )
        weights_df = compute_engine_weights(pipeline_results)
        _record_stage_timing("engine_weights", stage_started_at)
        if weights_df is None or weights_df.empty:
            _fail_pipeline("[PIPELINE] Engine weight computation failed.")
        pipeline_results["weights_df"] = weights_df

        if stop_after == "engine_weights":
            _mark_run_state("partial", completed_stage="engine_weights")
            du.print_success("[PIPELINE] Stopped after engine scoring by request.")
            return _finalize_with_manifest_timing()

        # Step 5: Print family distribution
        if bool(getattr(app_config, "ENABLE_FAMILY_DISTRIBUTION_REPORT", True)):
            family_distribution_report.print_family_distribution_stats(samples_df)
        else:
            du.print_info("[PIPELINE] Family distribution report disabled by configuration.")

        # Step 6: Build feature matrix (+ optional metadata features)
        stage_started_at = perf_counter()
        _begin_stage("feature_matrix")
        _print_run_context_line(
            run_id=run_id,
            profile_id=profile_id,
            stage="feature_matrix",
            stop_after=stop_after,
            selected_models=model_list,
        )
        permission_features_df = build_permission_enrichment_frame(
            samples_df=samples_df,
            feature_flags=feature_flags,
        )
        extra_features_df = merge_sample_metadata_features(
            extra_features_df=pipeline_results.get("enriched_matrix"),
            samples_df=samples_df,
            feature_flags=feature_flags,
            permission_features_df=permission_features_df,
        )

        feature_df = generate_feature_matrix(weights_df, parsed_data, extra_features_df)
        manifest_context["permission_enrichment_degraded"] = bool(
            getattr(app_config, "RUNTIME_PERMISSION_ENRICHMENT_DEGRADED", False)
        )
        _record_stage_timing("feature_matrix", stage_started_at)
        if feature_df is None:
            _fail_pipeline("[PIPELINE] Feature matrix generation failed.")
        if isinstance(feature_df, pd.DataFrame):
            lifecycle_df = pipeline_results.get("engine_lifecycle")
            if isinstance(lifecycle_df, pd.DataFrame):
                include_col = "included_in_model_flag"
                observed_col = "observed_flag"
                canonical_col = "canonicalized_flag"
                if include_col in lifecycle_df.columns:
                    include_mask = lifecycle_df[include_col].fillna(False).astype(bool)
                    included = int(include_mask.sum())
                    excluded = int((~include_mask).sum())
                else:
                    included = int(len(lifecycle_df))
                    excluded = 0
                observed = int(
                    lifecycle_df[observed_col].fillna(False).astype(bool).sum()
                ) if observed_col in lifecycle_df.columns else int(len(lifecycle_df))
                canonical = int(
                    lifecycle_df[canonical_col].fillna(False).astype(bool).sum()
                ) if canonical_col in lifecycle_df.columns else int(lifecycle_df["engine_name_canonical"].nunique())
                feature_df.attrs["engine_included_count"] = included
                feature_df.attrs["engine_excluded_count"] = excluded
                feature_df.attrs["engine_observed_count"] = observed
                feature_df.attrs["engine_canonical_count"] = canonical
                manifest_context["engine_count_observed"] = observed
                manifest_context["engine_count_canonical"] = canonical
                manifest_context["included_engine_count"] = included
                manifest_context["excluded_engine_count"] = excluded
                setattr(app_config, "RUNTIME_INCLUDED_ENGINE_COUNT", included)
            selected_vendors = list(feature_df.attrs.get("selected_vendors", []))
            min_selected = int(getattr(app_config, "FEATURE_MIN_SELECTED_VENDORS", 1))
            manifest_context["selected_vendor_count"] = len(selected_vendors)
            manifest_context["selected_vendors"] = selected_vendors
            manifest_context["vendor_constrained_run_flag"] = len(selected_vendors) < min_selected
            manifest_context["k_requested"] = int(feature_df.attrs.get("feature_top_k", getattr(app_config, "FEATURE_TOP_K", 0)) or 0)
            manifest_context["effective_top_k"] = int(feature_df.attrs.get("feature_effective_top_k", 0) or 0)
            manifest_context["vendor_fallback_used"] = bool(feature_df.attrs.get("vendor_fallback_used", False))
            manifest_context["vendor_fallback_added_count"] = int(feature_df.attrs.get("vendor_fallback_added_count", 0) or 0)
            manifest_context["non_standard_features"] = bool(feature_df.attrs.get("non_standard_features", False))

        if bool(getattr(app_config, "ENABLE_FEATURE_CONTRACT_EXPORT", True)):
            feature_contract_path = export_feature_contract(
                feature_df=feature_df,
                run_id=run_id,
                output_dir=DIAGNOSTICS_DIR,
            )
            if feature_contract_path:
                artifact_list.append(feature_contract_path)
                du.print_info(f"[ARTIFACT] Feature contract exported: {feature_contract_path}")

        if bool(getattr(app_config, "ENABLE_LEAKAGE_ASSESSMENT_EXPORT", True)):
            leakage_path = export_leakage_assessment(
                feature_df=feature_df,
                run_id=run_id,
                output_dir=DIAGNOSTICS_DIR,
            )
            if leakage_path:
                artifact_list.append(leakage_path)
                du.print_info(f"[ARTIFACT] Leakage assessment exported: {leakage_path}")
        modality_contract_path = export_modality_method_contract(
            permission_df=permission_features_df,
            fusion_feature_df=feature_df,
            run_id=run_id,
            output_dir=DIAGNOSTICS_DIR,
        )
        if modality_contract_path:
            artifact_list.append(modality_contract_path)
            du.print_info(f"[ARTIFACT] Modality method contract exported: {modality_contract_path}")

        if stop_after == "feature_matrix":
            _mark_run_state("partial", completed_stage="feature_matrix")
            du.print_success("[PIPELINE] Stopped after feature matrix build by request.")
            return _finalize_with_manifest_timing()

        # Step 7: Align features and labels
        stage_started_at = perf_counter()
        _begin_stage("alignment")
        _print_run_context_line(
            run_id=run_id,
            profile_id=profile_id,
            stage="alignment",
            stop_after=stop_after,
            selected_models=model_list,
        )
        aligned_feature_df, aligned_labels_df = run_feature_alignment_stage(
            feature_df=feature_df,
            samples_df=samples_df,
            diagnostics_dir=DIAGNOSTICS_DIR,
        )
        _record_stage_timing("alignment", stage_started_at)
        if aligned_feature_df is None or aligned_labels_df is None:
            _fail_pipeline("[PIPELINE] Feature-label alignment failed.")
        _export_aligned_training_cache(
            aligned_feature_df=aligned_feature_df,
            aligned_labels_df=aligned_labels_df,
            artifact_list=artifact_list,
        )
        _enforce_duplicate_sha_policy(
            aligned_labels_df=aligned_labels_df,
            run_id=run_id,
            artifact_list=artifact_list,
            manifest_context=manifest_context,
        )

        if stop_after == "alignment":
            _mark_run_state("partial", completed_stage="alignment")
            du.print_success("[PIPELINE] Stopped after feature-label alignment by request.")
            return _finalize_with_manifest_timing()

        # Step 8: Train classifiers
        stage_started_at = perf_counter()
        model_list = model_list or list(profile.get("model_list", []))
        _begin_stage("training")
        _print_run_context_line(
            run_id=run_id,
            profile_id=profile_id,
            stage="training",
            stop_after=stop_after,
            selected_models=model_list,
        )
        model_results = run_training_stage(
            aligned_feature_df=aligned_feature_df,
            aligned_labels_df=aligned_labels_df,
            model_list=model_list,
        )
        _record_stage_timing("training", stage_started_at)
        if not model_results:
            _fail_pipeline("[PIPELINE] Model training returned no results.")
        model_summary = _extract_model_summary(model_results)
        if model_summary:
            manifest_context["model_summary"] = model_summary
        _export_model_config_snapshot(
            run_id=run_id,
            model_results=model_results,
            artifact_list=artifact_list,
            manifest_context=manifest_context,
        )
        top_model_for_policy = None
        if isinstance(model_summary, dict):
            top_model_for_policy = str(model_summary.get("top_model") or "").strip() or None
        split_meta = getattr(app_config, "RUNTIME_SPLIT_METADATA", None)
        if isinstance(split_meta, dict):
            manifest_context["split"] = dict(split_meta)
            split_audit_path = split_meta.get("split_audit_path")
            if isinstance(split_audit_path, str) and split_audit_path:
                if split_audit_path not in artifact_list:
                    artifact_list.append(split_audit_path)

        if stop_after == "training":
            _mark_run_state("partial", completed_stage="training")
            _apply_confusion_matrix_policy(run_id=run_id, top_model=top_model_for_policy)
            du.print_success("[PIPELINE] Stopped after model training by request.")
            return _finalize_with_manifest_timing()

        run_ablation_flag = bool(getattr(app_config, "ENABLE_ABLATION_EXPERIMENTS", False))
        skip_ablation_for_single_model = bool(
            getattr(app_config, "SKIP_ABLATIONS_FOR_SINGLE_MODEL", True)
        )
        if (
            run_ablation_flag
            and not (skip_ablation_for_single_model and model_list and len(model_list) == 1)
        ):
            stage_started_at = perf_counter()
            _begin_stage("ablation")
            ablation_artifacts = run_ablation_experiments(
                samples_df=samples_df,
                weights_df=weights_df,
                parsed_data=parsed_data,
                permission_features_df=permission_features_df,
                model_list=model_list,
                run_id=run_id,
            )
            _record_stage_timing("ablation", stage_started_at)
            for artifact_path in ablation_artifacts:
                if artifact_path not in artifact_list:
                    artifact_list.append(artifact_path)
        elif run_ablation_flag and skip_ablation_for_single_model and model_list and len(model_list) == 1:
            du.print_info(
                "[ABLATION] Skipped for single-model run "
                "(set SKIP_ABLATIONS_FOR_SINGLE_MODEL=False to force)."
            )
        _apply_confusion_matrix_policy(run_id=run_id, top_model=top_model_for_policy)

        if stop_after == "ablation":
            _mark_run_state("partial", completed_stage="ablation")
            du.print_success("[PIPELINE] Stopped after ablation stage by request.")
            return _finalize_with_manifest_timing()

        permission_trends_enabled = bool(getattr(app_config, "ENABLE_PERMISSION_TRENDS_REPORT", True))
        if permission_trends_enabled:
            stage_started_at = perf_counter()
            _begin_stage("permission_trends")
            report_artifacts = run_permission_trends_report_stage(
                samples_df=samples_df,
                permission_features_df=permission_features_df,
                parsed_data=parsed_data,
                model_results=model_results,
                run_id=run_id,
                profile_id=profile_id,
                feature_df=feature_df,
            )
            _record_stage_timing("permission_trends", stage_started_at)
            for artifact_path in report_artifacts:
                if artifact_path not in artifact_list:
                    artifact_list.append(artifact_path)
        elif stop_after == "permission_trends":
            _mark_run_state("partial", completed_stage="ablation")
            du.print_warning(
                "[PIPELINE] stop_after='permission_trends' requested but "
                "permission trends are disabled; stopping after ablation/training."
            )
            return _finalize_with_manifest_timing()

        if stop_after == "permission_trends":
            _mark_run_state("partial", completed_stage="permission_trends")
            du.print_success("[PIPELINE] Stopped after permission trends stage by request.")
            return _finalize_with_manifest_timing()

        # Step 9: Final label resolution
        label_resolution_enabled = bool(getattr(app_config, "ENABLE_LABEL_RESOLUTION_STAGE", True))
        if label_resolution_enabled:
            stage_started_at = perf_counter()
            _begin_stage("label_resolution")
            _print_run_context_line(
                run_id=run_id,
                profile_id=profile_id,
                stage="label_resolution",
                stop_after=stop_after,
                selected_models=model_list,
            )
            df_labels = resolve_final_labels(vendor_records, model_results)
            _record_stage_timing("label_resolution", stage_started_at)
            if df_labels is not None:
                du.print_info(f"[PIPELINE] Final labels generated: {len(df_labels)} samples")
        else:
            du.print_info("[PIPELINE] Label resolution stage disabled by configuration.")

        if stop_after == "label_resolution":
            _mark_run_state(
                "partial",
                completed_stage="label_resolution" if label_resolution_enabled else "permission_trends",
            )
            if not label_resolution_enabled:
                du.print_warning(
                    "[PIPELINE] stop_after='label_resolution' requested, but the stage is disabled."
                )
            du.print_success("[PIPELINE] Stopped after final label resolution by request.")
            return _finalize_with_manifest_timing()

        total_runtime_sec = max(0.0, perf_counter() - pipeline_started_at)
        du.print_info(f"[TIME] total_pipeline_runtime: {total_runtime_sec:.2f}s")
        log_event(
            PIPELINE_MAIN_LOGGER,
            "pipeline_timing_complete",
            run_id=run_id,
            total_runtime_sec=round(total_runtime_sec, 2),
            stages={k: round(v, 2) for k, v in stage_timings_sec.items()},
        )
        _attach_runtime_timing_context()
        run_summary_payload = _build_run_summary_payload(
            run_id=run_id,
            profile_id=profile_id,
            samples_df=samples_df,
            model_results=model_results if isinstance(model_results, dict) else {},
            top_model=top_model_for_policy,
            manifest_context=manifest_context,
        )
        _export_and_print_run_summary(payload=run_summary_payload, artifact_list=artifact_list)
        du.print_success("Classification pipeline executed successfully.")
        _mark_run_state("complete", completed_stage="manifest")
        _write_preflight(status="pass")
        return _finalize_with_manifest_timing()

    except Exception as e:
        error_text = str(e)
        if error_text.startswith("[INTEGRITY]"):
            du.print_error("[INTEGRITY STOP]")
        else:
            du.print_error(f"[CRITICAL] Pipeline crashed: {e}")
        _mark_run_state(
            "failed",
            failure_reason=error_text,
            failed_stage=current_stage_name or last_completed_stage,
        )
        _write_preflight(status="failed", reason=str(e))
        manifest_context["integrity_error"] = error_text

        # Avoid full tracebacks for expected profile/data failures
        if ml_console.is_debug() and not error_text.startswith("[PROFILE]") and not isinstance(e, _PipelineStageFailure):
            traceback.print_exc()
        elif error_text.startswith("[INTEGRITY]"):
            if "Missing package rate" in error_text:
                du.print_error(error_text.replace("[INTEGRITY] ", ""))
                if bool(getattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False)):
                    du.print_info(
                        "Action: use research_all_malicious profile for exploratory runs "
                        "or clean package metadata for evidence runs."
                    )

        if manifest_context.get("run_id"):
            _finalize_with_manifest_timing()
        if bool(getattr(app_config, "EVIDENCE_MODE_ENABLED", getattr(app_config, "PAPER_MODE_ENABLED", False))) and bool(
            getattr(
                app_config,
                "FAIL_FAST_PIPELINE_EXCEPTIONS_IN_EVIDENCE_MODE",
                getattr(app_config, "FAIL_FAST_PIPELINE_EXCEPTIONS_IN_PAPER_MODE", True),
            )
        ) and not error_text.startswith("[INTEGRITY]") and not error_text.startswith("[PROFILE]") and not isinstance(
            e, _PipelineStageFailure
        ):
            raise
        return 1
    finally:
        runtime_logging.stop_runtime_logging(runtime_log_context)
        logger_manager.close_all_loggers()
        for key, original_value in mutable_config_snapshot.items():
            if original_value is _CONFIG_MISSING:
                if hasattr(app_config, key):
                    try:
                        delattr(app_config, key)
                    except Exception:
                        pass
                continue
            try:
                setattr(app_config, key, original_value)
            except Exception:
                pass
        DIAGNOSTICS_DIR = original_diagnostics_dir


def _finalize_run_manifest(
    manifest_context: dict,
    profile: dict,
    samples_df: pd.DataFrame | None,
    pipeline_results: dict | None,
    vendor_eval_df: pd.DataFrame | None,
    artifact_list: list[str],
) -> int:
    """Backward-compatible wrapper for run-manifest finalization stage."""
    result_code = finalize_run_manifest_stage(
        manifest_context=manifest_context,
        profile=profile,
        samples_df=samples_df,
        pipeline_results=pipeline_results,
        vendor_eval_df=vendor_eval_df,
        artifact_list=artifact_list,
    )
    if result_code != 0:
        du.print_error("[INTEGRITY] Run manifest write failure.")
    return result_code


def main() -> int:
    """Execute the full malware classification workflow."""
    allow_override = "--allow-evidence-override" in sys.argv[1:]
    allow_global = "--allow-global-artifacts" in sys.argv[1:]
    return run_pipeline(
        allow_evidence_override=allow_override,
        allow_global_artifacts=allow_global,
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Pipeline aborted by user.")
        sys.exit(130)
