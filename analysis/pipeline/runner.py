"""Pipeline orchestration: profile loading, staged execution, manifest finalization.

This module holds ``run_pipeline`` and run-scoped helpers extracted from ``main.py``
so the CLI entry module stays thin and tests can import ``main.run_pipeline`` unchanged.
"""

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
from ml_classification.training.model_trainer_factory import reset_runtime_training_caches

# === Database + Utilities ===
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console
from obsidiandroid.reporting import family_distribution_report
import obsidiandroid.cli.profile_manager as profile_manager
import obsidiandroid.governance.run_manifest as run_manifest
from obsidiandroid.governance import evidence_mode_resolver
from obsidiandroid.observability.logging import runtime as runtime_logging
from obsidiandroid.observability.logging import logger as logger_manager
from obsidiandroid.observability.logging import get_logger, log_event
from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.common import output_hygiene as oh
from analysis.pipeline.governance.integrity import enforce_run_scoped_artifact_paths
from obsidiandroid.diagnostics import cohort_foundation_export
from obsidiandroid.diagnostics import cohort_sample_id_audit
from obsidiandroid.diagnostics import cohort_vocabulary
from obsidiandroid.diagnostics import feature_build_coverage_export
from obsidiandroid.diagnostics import fused_permission_matrix_audit
from obsidiandroid.diagnostics import permission_training_survival_audit

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
    clear_cross_run_artifact_path_pointers,
    enforce_paper_perturbation_axes as enforce_paper_perturbation_axes_policy,
    reset_runtime_markers,
)
from analysis.orchestration.methodology_artifacts import (
    export_feature_contract,
    export_leakage_assessment,
    export_modality_method_contract,
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
    format_population_pipeline_summary_line as _format_population_pipeline_summary_line,
    parse_key_value_meta as _parse_key_value_meta,
    print_run_context_line as _print_run_context_line,
    setup_runtime_context,
)
from obsidiandroid.database.db_sample_metadata_contracts import get_query_contract_metadata
from analysis.pipeline.main_facade import from_main_or
from analysis.pipeline.run_bounds import (
    PipelineRunBounds,
    clear_pipeline_run_bounds,
    set_pipeline_run_bounds,
)
from obsidiandroid.observability.pipeline_observability import PipelineObservabilitySession
from obsidiandroid.observability.pipeline_observability import api as obs_api
from obsidiandroid.observability.pipeline_observability.taxonomy import LogCategory, LogSeverity

# Default diagnostics path derived from app configuration
DIAGNOSTICS_DIR = os.path.join(app_config.DEFAULT_OUTPUT_DIR, "diagnostics")
# Keep legacy module constant for backward compatibility; use runtime-resolved
# path inside run_pipeline for paper-mode routing.
PARSER_QUALITY_PATH = Path(DIAGNOSTICS_DIR) / "parser_quality.latest.csv"
PIPELINE_MAIN_LOGGER = get_logger(
    f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.pipeline.main",
    "pipeline",
)
_CONFIG_MISSING = object()


def _sync_main_module_diagnostics(path: str) -> None:
    """Mirror diagnostics path onto ``main`` when loaded (tests patch ``main.DIAGNOSTICS_DIR``)."""
    main_mod = sys.modules.get("main")
    if main_mod is not None and hasattr(main_mod, "DIAGNOSTICS_DIR"):
        setattr(main_mod, "DIAGNOSTICS_DIR", path)


def _set_diagnostics_dir(path: str) -> None:
    """Update runner global diagnostics dir and keep ``main.DIAGNOSTICS_DIR`` in sync."""
    global DIAGNOSTICS_DIR
    DIAGNOSTICS_DIR = path
    _sync_main_module_diagnostics(path)


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
    # Clear cross-run path pointers before snapshot so a prior test/run cannot leave
    # files outside this run's RUNTIME_RUN_ROOT (strict artifact_list enforcement).
    clear_cross_run_artifact_path_pointers()
    # Drop per-run_id training split caches from earlier pytest cases / CLI invocations
    # so ``RUNTIME_TRAINING_STATE`` does not grow without bound and stays out of the way
    # of the snapshot/finally restore for this run.
    reset_runtime_training_caches()
    mutable_config_keys = build_mutable_config_keys()
    mutable_config_snapshot: dict[str, Any] = {
        key: getattr(app_config, key, _CONFIG_MISSING) for key in mutable_config_keys
    }
    setattr(app_config, "RUNTIME_RUN_ID", run_id)
    strict_run_scoped = True
    runtime_paths = setup_runtime_context(run_id=run_id, strict_run_scoped=True)
    output_root_base = runtime_paths["output_root_base"]
    runtime_run_root = runtime_paths["runtime_run_root"]
    _set_diagnostics_dir(str(runtime_paths["runtime_diagnostics_dir"]))
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

    def _record_stage_timing(
        stage_name: str,
        started_at: float,
        *,
        record_observability: bool = True,
        **obs_kwargs: Any,
    ) -> None:
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
        if not record_observability:
            return
        obs_sess = manifest_context.get("pipeline_observability")
        if isinstance(obs_sess, PipelineObservabilitySession):
            obs_copy = dict(obs_kwargs)
            wall_start = str(manifest_context.pop("_active_stage_wall_start_iso", "") or "").strip()
            extras: dict[str, Any] = dict(obs_copy.pop("extras", None) or {})
            if wall_start:
                extras.setdefault("start_time_iso", wall_start)
            stage_status = str(obs_copy.pop("stage_status", "PASS"))
            emit_keys = (
                "input_rows",
                "output_rows",
                "input_features",
                "output_features",
                "rows_removed",
                "rows_added",
                "features_removed",
                "features_added",
                "major_warnings",
                "paper_blocker_stage",
                "artifacts_written_count",
                "artifacts_skipped",
                "next_stage_allowed",
            )
            emit_kw: dict[str, Any] = {}
            for key in emit_keys:
                if key in obs_copy:
                    emit_kw[key] = obs_copy.pop(key)
            extras.update(obs_copy)
            obs_sess.emit_stage_completion(
                stage_name,
                status=stage_status,
                duration_sec=duration,
                extras=extras,
                **emit_kw,
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
        manifest_context["_active_stage_wall_start_iso"] = datetime.now(timezone.utc).isoformat()
        obs_begin = manifest_context.get("pipeline_observability")
        if isinstance(obs_begin, PipelineObservabilitySession):
            obs_begin.emit_stage_start(stage_name, stop_after=str(manifest_context.get("stop_after", "")))

    def _attach_runtime_timing_context() -> None:
        total_runtime = max(0.0, perf_counter() - pipeline_started_at)
        manifest_context["stage_timings_sec"] = {
            k: round(v, 3) for k, v in stage_timings_sec.items()
        }
        manifest_context["pipeline_runtime_sec"] = round(total_runtime, 3)
        if last_completed_stage and "completed_stage" not in manifest_context:
            manifest_context["completed_stage"] = last_completed_stage
        if stage_timings_sec:
            timings_df = pd.DataFrame(
                [
                    {"stage": stage, "duration_sec": round(duration, 3)}
                    for stage, duration in stage_timings_sec.items()
                ]
            )
            timings_df["run_id"] = run_id
            timings_df["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
            timings_csv = timings_df.to_csv(index=False)
            t_paths = oh.mirror_csv_text_run_then_global(
                diagnostics_dir=Path(DIAGNOSTICS_DIR),
                run_filename=f"pipeline_stage_timings_{run_id}.csv",
                csv_text=timings_csv,
                global_latest_name="pipeline_stage_timings.latest.csv",
            )
            for p in t_paths:
                sp = str(p)
                if sp not in artifact_list:
                    artifact_list.append(sp)

    def _finalize_with_manifest_timing() -> int:
        """Finalize run manifest and record manifest stage timing."""
        stage_started = perf_counter()
        _attach_runtime_timing_context()
        result = from_main_or("finalize_run_manifest_stage", finalize_run_manifest_stage)(
            manifest_context=manifest_context,
            profile=profile,
            samples_df=samples_df,
            pipeline_results=pipeline_results,
            vendor_eval_df=vendor_eval,
            artifact_list=artifact_list,
        )
        if result != 0:
            du.print_error("[INTEGRITY] Run manifest write failure.")
        _record_stage_timing("manifest", stage_started, record_observability=False)
        _attach_runtime_timing_context()
        return result

    def _write_preflight(status: str, reason: str = "") -> None:
        """Write evidence-mode preflight report for auditability."""
        nonlocal preflight_path, preflight_payload
        evidence_on = bool(
            getattr(
                app_config,
                "EVIDENCE_MODE_ENABLED",
                getattr(app_config, "PAPER_MODE_ENABLED", False),
            )
        )
        samples_cohort_audit = str(stop_after).strip().lower() == "samples"
        if not evidence_on and not samples_cohort_audit:
            return
        run_root = Path(str(getattr(app_config, "RUNTIME_RUN_ROOT", app_config.DEFAULT_OUTPUT_DIR)))
        diagnostics_dir = run_root / "diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        if preflight_path is None:
            preflight_path = diagnostics_dir / "preflight_report.json"
        if samples_cohort_audit:
            preflight_payload[cohort_vocabulary.KEY_SAMPLES_STAGE_COHORT_COUNTS] = {
                "stop_after": stop_after,
                "cohort_sql_scope_row_count": manifest_context.get("cohort_sql_scope_row_count"),
                "cohort_prepared_row_count": manifest_context.get("cohort_prepared_row_count"),
            }
        if manifest_context.get("cohort_distinct_sample_id") is not None:
            preflight_payload["cohort_sample_id_integrity"] = {
                "cohort_prepared_row_count": manifest_context.get("cohort_prepared_row_count"),
                "cohort_distinct_sample_id": manifest_context.get("cohort_distinct_sample_id"),
                "cohort_duplicate_surplus_rows": manifest_context.get("cohort_duplicate_surplus_rows"),
            }
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
        du.print_info(
            f"[PIPELINE] Scope: stop_after={stop_after} | profile_ref={profile_ref}"
        )
        du.print_info(
            f"[PIPELINE] Paths: output_root={output_root_base} | "
            f"run_root={runtime_run_root} | diagnostics={DIAGNOSTICS_DIR}"
        )
        if runtime_log_context is not None:
            du.print_info(f"[LOG] Runtime stream log: {runtime_log_context.log_path}")

        # Ensure diagnostics directory exists
        os.makedirs(DIAGNOSTICS_DIR, exist_ok=True)

        manifest_context["pipeline_observability"] = PipelineObservabilitySession(
            diagnostics_dir=Path(DIAGNOSTICS_DIR),
            run_id=run_id,
        )

        # Load profile
        du.print_info("[PIPELINE] Loading profile YAML...")
        profile = from_main_or("profile_manager", profile_manager).load_profile(profile_ref)
        du.print_info(
            f"[PIPELINE] Profile: id={profile.get('profile_id')} | file={profile.get('__profile_path', '')}"
        )
        requested_evidence_mode = (
            evidence_mode_override if evidence_mode_override is not None else paper_mode_override
        )
        env_evidence_value = os.environ.get(evidence_mode_resolver.ENV_EVIDENCE_MODE)
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
        if evidence_mode_source == "default_profile_ineligible":
            manifest_context["evidence_mode"]["downgrade_reason"] = (
                "Resolution was default without evidence_perturbation_axes; "
                "evidence mode disabled for safety."
            )
        manifest_context["paper_mode"] = dict(manifest_context["evidence_mode"])
        # mode_effective: strict run-scoped / paper-style contract. resolution_source: cli|env|profile|default
        # (source=profile + mode_effective=False means the YAML set evidence_mode: false, not a bug.)
        du.print_info(
            f"[EVIDENCE] mode_effective={effective_evidence_mode} "
            f"resolution_source={evidence_mode_source} "
            f"profile_evidence_mode={profile.get('evidence_mode')!r}"
        )
        if effective_evidence_mode:
            run_root = output_root_base / "runs" / run_id
            run_root.mkdir(parents=True, exist_ok=True)
            setattr(app_config, "RUNTIME_RUN_ROOT", str(run_root))
            setattr(app_config, "DEFAULT_OUTPUT_DIR", str(run_root))
            _set_diagnostics_dir(str(run_root / "diagnostics"))
            setattr(
                app_config,
                "ANALYSIS_SNAPSHOT_FILE",
                str(Path(DIAGNOSTICS_DIR) / f"analysis_snapshot_{run_id}.csv"),
            )
            setattr(
                app_config,
                "ANALYSIS_SNAPSHOT_META_FILE",
                str(Path(DIAGNOSTICS_DIR) / f"analysis_snapshot_{run_id}.meta.txt"),
            )
            setattr(
                app_config,
                "ANALYSIS_SNAPSHOT_CONFLICT_FILE",
                str(Path(DIAGNOSTICS_DIR) / f"analysis_snapshot_label_conflicts_{run_id}.csv"),
            )
            setattr(
                app_config,
                "PAPER_COHORT_SAMPLE_IDS_FILE",
                str(Path(DIAGNOSTICS_DIR) / "paper_cohort_sample_ids.csv"),
            )
            setattr(
                app_config,
                "DATASET_TIME_CONTRACT_FILE",
                str(Path(DIAGNOSTICS_DIR) / f"dataset_time_contract_{run_id}.json"),
            )
            setattr(
                app_config,
                "ALIGNED_FEATURE_CACHE_FILE",
                str(Path(DIAGNOSTICS_DIR) / f"aligned_features_{run_id}.csv.gz"),
            )
            setattr(
                app_config,
                "ALIGNED_LABEL_CACHE_FILE",
                str(Path(DIAGNOSTICS_DIR) / f"aligned_labels_{run_id}.csv"),
            )
            du.print_info(f"[EVIDENCE] Run root: {run_root}")
        # Stable snapshot after evidence/paper path remapping (DEFAULT_OUTPUT_DIR / diagnostics).
        set_pipeline_run_bounds(
            PipelineRunBounds(
                run_id=run_id,
                profile_ref=str(
                    (profile.get("profile_id") if isinstance(profile, dict) else None) or profile_ref or ""
                ),
                stop_after=stop_after,
                diagnostics_dir=Path(DIAGNOSTICS_DIR),
                output_root_base=Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root_base)))),
                runtime_run_root=Path(str(getattr(app_config, "RUNTIME_RUN_ROOT", str(runtime_run_root)))),
            )
        )
        enforce_paper_perturbation_axes_policy(profile=profile, paper_mode=effective_evidence_mode)
        runtime_log_context = from_main_or("runtime_logging", runtime_logging).start_runtime_logging(
            run_id
        )
        if runtime_log_context is not None:
            artifact_list.append(str(runtime_log_context.log_path))
        manifest_context["profile_params"] = profile
        manifest_context["config_hash"] = hash_payload(profile)
        du.print_info("[PIPELINE] Metadata: dependency versions + DB query contract...")
        manifest_context["dependency_versions"] = _collect_dependency_versions()
        manifest_context["db_query_contract"] = get_query_contract_metadata()
        _write_preflight(status="running")

        feature_flags = profile.get("feature_flags", {}) if isinstance(profile, dict) else {}
        du.print_info("[PIPELINE] Applying runtime policy (feature flags, evidence strictness)...")
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

        preflight_perf = perf_counter()
        _begin_stage("preflight")

        # Step 1: Load and prepare sample metadata
        wall_pf = manifest_context.pop("_active_stage_wall_start_iso", "")
        obs_pf = manifest_context.get("pipeline_observability")
        if isinstance(obs_pf, PipelineObservabilitySession):
            ex_pf: dict[str, Any] = {}
            if wall_pf:
                ex_pf["start_time_iso"] = str(wall_pf)
            obs_pf.emit_stage_completion(
                "preflight",
                status="PASS",
                duration_sec=max(0.0, perf_counter() - preflight_perf),
                next_stage_allowed=True,
                extras=ex_pf,
            )
        du.print_info(
            f"[PIPELINE] Stage: samples - fetching cohort (type_slug={type_slug!r})..."
        )
        stage_started_at = perf_counter()
        _begin_stage("samples")
        _print_run_context_line(
            run_id=run_id,
            profile_id=profile_id,
            stage="samples",
            stop_after=stop_after,
            selected_models=model_list,
        )
        samples_df = from_main_or("load_and_prepare_samples", load_and_prepare_samples)(
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
        gs = samples_df.attrs.get("cohort_gate_stats") or {}
        sql_scope_rows = int(gs.get("total_candidates", 0) or 0)
        prepared_rows = int(len(samples_df))
        cohort_vocabulary.attach_cohort_row_counts_to_manifest_context(
            manifest_context,
            sql_scope_row_count=sql_scope_rows,
            prepared_row_count=prepared_rows,
        )
        cohort_foundation_export.append_research_warnings_for_upstream_expectation(
            manifest_context,
            profile_id=profile_id,
            sql_scope_row_count=sql_scope_rows,
            gates=profile.get("cohort_gates", {}) if isinstance(profile, dict) else {},
        )
        obs_sess = manifest_context.get("pipeline_observability")
        raw_n_for_obs = sql_scope_rows if sql_scope_rows > 0 else prepared_rows
        if isinstance(obs_sess, PipelineObservabilitySession):
            obs_sess.log_population_transition(
                transition="cohort_sql_scope_to_prepared_rows",
                previous_count=int(raw_n_for_obs),
                new_count=int(len(samples_df)),
                reason="SQL profile cohort scope → samples_df after fetch + Python preparation",
                artifact_path=str(snapshot_file),
            )
        _record_stage_timing(
            "samples",
            stage_started_at,
            input_rows=int(raw_n_for_obs),
            output_rows=int(len(samples_df)),
        )
        if samples_df is None or samples_df.empty:
            raise ValueError("No samples found after preparation.")

        _sid_audit = cohort_sample_id_audit.audit_cohort_sample_id_uniqueness(
            samples_df,
            diagnostics_dir=Path(DIAGNOSTICS_DIR),
            run_id=run_id,
            artifact_list=artifact_list,
        )
        cohort_sample_id_audit.merge_sample_id_audit_into_manifest(manifest_context, _sid_audit)

        if stop_after == "samples":
            _mark_run_state("partial", completed_stage="samples")
            _write_preflight(
                status="stopped_after_samples",
                reason="stop_after=samples (cohort audit; later stages skipped)",
            )
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
        pipeline_results = from_main_or("run_av_analysis_stage", run_av_analysis_stage)(
            samples_df=samples_df,
            run_id=run_id,
            profile_id=profile_id,
            artifact_list=artifact_list,
            manifest_context=manifest_context,
        )
        if not pipeline_results:
            _record_stage_timing(
                "av_pipeline",
                stage_started_at,
                stage_status="FAIL",
                input_rows=int(len(samples_df)),
                major_warnings="av_pipeline_returned_empty",
            )
            _fail_pipeline("[PIPELINE] AV pipeline returned no results.")
        eng_preview = pipeline_results.get("engine_scores") if isinstance(pipeline_results, dict) else None
        eng_out_rows: int | str = ""
        if isinstance(eng_preview, pd.DataFrame) and not eng_preview.empty:
            eng_out_rows = int(
                len(eng_preview["sample_id"].unique())
                if "sample_id" in eng_preview.columns
                else len(eng_preview)
            )
        _record_stage_timing(
            "av_pipeline",
            stage_started_at,
            input_rows=int(len(samples_df)),
            output_rows=eng_out_rows,
            major_warnings="",
        )
        eng_overlay_csv = str(getattr(app_config, "RUNTIME_ENGINE_METADATA_OVERLAY_CSV", "") or "").strip()
        if eng_overlay_csv:
            manifest_context["engine_metadata_overlay_csv"] = eng_overlay_csv
            if eng_overlay_csv not in artifact_list:
                artifact_list.append(eng_overlay_csv)

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
        if isinstance(vendor_eval, pd.DataFrame) and "sample_id" in vendor_eval.columns:
            ve_n = int(vendor_eval["sample_id"].nunique())
            manifest_context["vendor_eval_sample_rows"] = ve_n
            obs_api.record_data_population_change(
                manifest_context,
                transition="prepared_cohort_to_vendor_feature_rows",
                previous_count=int(len(samples_df)),
                new_count=ve_n,
                reason="unique samples represented in vendor_eval after metadata extraction",
                artifact_path=str(parser_quality_path) if parser_quality_path.exists() else "",
            )

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
        weights_df = compute_engine_weights_from_pipeline(pipeline_results)
        _record_stage_timing(
            "engine_weights",
            stage_started_at,
            output_rows=int(len(weights_df)) if weights_df is not None else "",
        )
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
        if isinstance(permission_features_df, pd.DataFrame) and not permission_features_df.empty:
            manifest_context["permission_unique_rows"] = int(
                permission_features_df["sample_id"].nunique()
            )
            obs_sess = manifest_context.get("pipeline_observability")
            if isinstance(obs_sess, PipelineObservabilitySession):
                obs_sess.log_population_transition(
                    transition="prepared_cohort_to_permission_feature_rows",
                    previous_count=int(len(samples_df)),
                    new_count=int(permission_features_df["sample_id"].nunique()),
                    reason="samples with enrichment join coverage (sparse if DB gaps)",
                    artifact_path=str(Path(DIAGNOSTICS_DIR) / f"permission_feature_audit_{run_id}.csv"),
                )
            try:
                setattr(
                    app_config,
                    "RUNTIME_PERMISSION_FRAME_SAMPLE_IDS",
                    sorted(
                        feature_build_coverage_export._normalize_sample_ids(
                            permission_features_df["sample_id"]
                        )
                    ),
                )
            except Exception:
                pass
        extra_features_df = merge_sample_metadata_features(
            extra_features_df=pipeline_results.get("enriched_matrix"),
            samples_df=samples_df,
            feature_flags=feature_flags,
            permission_features_df=permission_features_df,
        )
        perm_fuse_audit = getattr(app_config, "RUNTIME_PERMISSION_FUSE_AUDIT", None)
        if isinstance(perm_fuse_audit, dict) and perm_fuse_audit:
            manifest_context["permission_fuse_audit"] = dict(perm_fuse_audit)
        dup_csv = str(getattr(app_config, "RUNTIME_DUPLICATE_SAMPLE_ID_PRE_FUSE_CSV", "") or "").strip()
        if dup_csv:
            manifest_context["duplicate_sample_id_pre_fuse_csv"] = dup_csv

        try:
            feature_df = build_feature_matrix_stage(
                weights_df,
                parsed_data,
                extra_features_df,
                cohort_sample_ids=samples_df["sample_id"],
            )
        except Exception as e:
            du.print_error(f"[ERROR] Feature matrix generation failed: {e}")
            feature_df = None
        manifest_context["permission_enrichment_degraded"] = bool(
            getattr(app_config, "RUNTIME_PERMISSION_ENRICHMENT_DEGRADED", False)
        )
        if feature_df is None:
            _fail_pipeline("[PIPELINE] Feature matrix generation failed.")
        fused_rows = int(len(feature_df))
        fused_cols = int(feature_df.shape[1])
        obs_sess_fm = manifest_context.get("pipeline_observability")
        if isinstance(obs_sess_fm, PipelineObservabilitySession):
            gov_n_fm = int(manifest_context.get("cohort_prepared_row_count", len(samples_df)) or len(samples_df))
            cov_path_hint = Path(DIAGNOSTICS_DIR) / f"feature_build_coverage_{run_id}.json"
            obs_sess_fm.log_population_transition(
                transition="prepared_cohort_to_fused_vendor_feature_rows",
                previous_count=gov_n_fm,
                new_count=int(fused_rows),
                reason="governed cohort rows (vendor gaps unknown/zero-filled; PI/metadata from enrichment)",
                artifact_path=str(cov_path_hint),
            )
        _record_stage_timing(
            "feature_matrix",
            stage_started_at,
            input_rows=int(manifest_context.get("cohort_prepared_row_count", len(samples_df)) or 0),
            output_rows=fused_rows,
            input_features=fused_cols,
            output_features=fused_cols,
        )
        if isinstance(feature_df, pd.DataFrame):
            manifest_context["fused_feature_rows"] = int(len(feature_df))
            manifest_context["feature_matrix_row_authority"] = str(
                feature_df.attrs.get("feature_matrix_row_authority") or ""
            )
            try:
                vm_list = feature_df.attrs.get("vendor_merge_sample_ids")
                if isinstance(vm_list, list):
                    setattr(
                        app_config,
                        "RUNTIME_VENDOR_MERGE_SAMPLE_IDS",
                        sorted(feature_build_coverage_export._normalize_sample_ids(vm_list)),
                    )
                setattr(
                    app_config,
                    "RUNTIME_FUSED_MATRIX_SAMPLE_IDS",
                    sorted(feature_build_coverage_export._matrix_row_sample_ids(feature_df)),
                )
                setattr(
                    app_config,
                    "RUNTIME_GOVERNED_COHORT_SAMPLE_IDS",
                    sorted(
                        feature_build_coverage_export._normalize_sample_ids(samples_df["sample_id"])
                    ),
                )
                setattr(
                    app_config,
                    "RUNTIME_PERM_SURVIVAL_COHORT_FUSED_BUNDLE",
                    (
                        permission_training_survival_audit.perm_prefix_nonzero_stats(feature_df),
                        int(len(feature_df)),
                    ),
                )
            except Exception:
                pass
            manifest_context["vendor_merge_row_count"] = int(
                feature_df.attrs.get(
                    "vendor_merge_sample_id_count",
                    len(feature_df.index),
                )
                or 0
            )
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

            fused_perm_sig = fused_permission_matrix_audit.summarize_fused_permission_columns(feature_df)
            if fused_perm_sig:
                manifest_context["fused_permission_matrix_signal"] = fused_perm_sig
                for k, v in sorted(fused_perm_sig.items()):
                    du.print_info(f"[FEATURES][PERM_MATRIX] {k}={v}")
                try:
                    fuse_audit = manifest_context.get("permission_fuse_audit")
                    enrich_any = None
                    if isinstance(fuse_audit, dict):
                        enrich_any = fuse_audit.get(
                            "post_fuse_enrichment_rows_with_any_perm_bag_column_positive"
                        )
                    fused_any = fused_perm_sig.get(
                        "fused_matrix_rows_with_any_perm_like_positive"
                    )
                    perm_matrix_row_count = fused_perm_sig.get("fused_matrix_row_count")
                    cohort_n = manifest_context.get("cohort_prepared_row_count")
                    if (
                        enrich_any is not None
                        and fused_any is not None
                        and perm_matrix_row_count is not None
                        and cohort_n is not None
                    ):
                        cohort_i = int(cohort_n)
                        fused_i = int(perm_matrix_row_count)
                        gap = max(0, cohort_i - fused_i)
                        if (
                            int(enrich_any) >= 50
                            and int(fused_any) <= max(10, int(enrich_any) // 10)
                            and gap >= 50
                        ):
                            du.print_info(
                                "[FEATURES][PERM_MATRIX] note=enrichment shows many cohort rows with "
                                "permission bag signal, but the fused ML matrix is vendor-authoritative "
                                "(fewer rows). Permission positives often concentrate on samples dropped "
                                "by vendor/parser gates; compare cohort_n, fused rows, and "
                                "feature_build_coverage / unmatched_label_ids exports."
                                f" cohort_n={cohort_i} fused_rows={fused_i} cohort_minus_fused_rows={gap} "
                                f"enrichment_any_perm_rows≈{int(enrich_any)} "
                                f"fused_any_perm_rows={int(fused_any)}"
                            )
                except Exception:
                    pass

            if bool(getattr(app_config, "ENABLE_FEATURE_BUILD_COVERAGE_EXPORT", True)):
                cov_path, _cov_csv_path = feature_build_coverage_export.export_feature_build_coverage(
                    cohort_sample_ids=samples_df["sample_id"],
                    feature_df=feature_df,
                    output_dir=DIAGNOSTICS_DIR,
                    run_id=run_id,
                    permission_features_df=permission_features_df
                    if isinstance(permission_features_df, pd.DataFrame)
                    else None,
                )
                if cov_path:
                    artifact_list.append(str(cov_path))
                _mod_csv, _mod_json = feature_build_coverage_export.export_feature_modality_coverage_audit(
                    cohort_sample_ids=samples_df["sample_id"],
                    feature_df=feature_df,
                    permission_features_df=permission_features_df
                    if isinstance(permission_features_df, pd.DataFrame)
                    else None,
                    output_dir=DIAGNOSTICS_DIR,
                    run_id=run_id,
                    samples_df=samples_df,
                )
                if _mod_csv:
                    artifact_list.append(str(_mod_csv))
                if _mod_json:
                    artifact_list.append(str(_mod_json))
                _gate_path = feature_build_coverage_export.export_feature_matrix_lineage_gate(
                    samples_df=samples_df,
                    feature_df=feature_df,
                    output_dir=DIAGNOSTICS_DIR,
                    run_id=run_id,
                )
                if _gate_path:
                    artifact_list.append(str(_gate_path))

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
        if aligned_feature_df is None or aligned_labels_df is None:
            _fail_pipeline("[PIPELINE] Feature-label alignment failed.")
        manifest_context["aligned_supervised_rows"] = int(len(aligned_feature_df))
        manifest_context["_aligned_feature_cols"] = int(aligned_feature_df.shape[1])
        obs_al = manifest_context.get("pipeline_observability")
        if isinstance(obs_al, PipelineObservabilitySession):
            split_audit_guess = str(Path(DIAGNOSTICS_DIR) / f"split_freeze_audit_{run_id}.csv")
            obs_al.log_population_transition(
                transition="fused_features_to_aligned_supervised",
                previous_count=int(fused_rows),
                new_count=int(len(aligned_feature_df)),
                reason="ROW_ALIGNMENT align_data intersection on sample_id (+ label completeness)",
                artifact_path=split_audit_guess,
            )
        obs_api.record_data_population_change(
            manifest_context,
            transition="feature_matrix_rows_to_aligned_rows",
            previous_count=int(fused_rows),
            new_count=int(len(aligned_feature_df)),
            reason="explicit feature-matrix→aligned labeling view (matches fusion→alignment drop)",
            artifact_path=str(Path(DIAGNOSTICS_DIR) / f"split_freeze_audit_{run_id}.csv"),
        )
        _record_stage_timing(
            "alignment",
            stage_started_at,
            input_rows=int(fused_rows),
            output_rows=int(len(aligned_feature_df)),
            input_features=int(fused_cols),
            output_features=int(aligned_feature_df.shape[1]),
        )
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
        split_audit_path_str = ""
        if isinstance(split_meta, dict):
            manifest_context["split"] = dict(split_meta)
            manifest_context["train_sample_count"] = split_meta.get("train_sample_count")
            manifest_context["test_sample_count"] = split_meta.get("test_sample_count")
            split_audit_path = split_meta.get("split_audit_path")
            if isinstance(split_audit_path, str) and split_audit_path:
                split_audit_path_str = split_audit_path
                if split_audit_path not in artifact_list:
                    artifact_list.append(split_audit_path)
        manifest_context["post_low_support_training_rows"] = getattr(
            app_config, "RUNTIME_POST_LOW_SUPPORT_TRAINING_ROWS", None
        )
        perm_surv_csv = str(getattr(app_config, "RUNTIME_PERMISSION_TRAINING_SURVIVAL_CSV", "") or "").strip()
        if perm_surv_csv:
            manifest_context["permission_training_survival_csv"] = perm_surv_csv
            if perm_surv_csv not in artifact_list:
                artifact_list.append(perm_surv_csv)
        feat_surv_csv = str(getattr(app_config, "RUNTIME_FEATURE_COLUMN_SURVIVAL_CSV", "") or "").strip()
        if feat_surv_csv:
            manifest_context["feature_column_survival_csv"] = feat_surv_csv
            if feat_surv_csv not in artifact_list:
                artifact_list.append(feat_surv_csv)
        try:
            _lineage_p = feature_build_coverage_export.export_sample_stage_lineage_audit(
                cohort_sample_ids=samples_df["sample_id"],
                output_dir=DIAGNOSTICS_DIR,
                run_id=run_id,
            )
            if _lineage_p:
                manifest_context["sample_stage_lineage_csv"] = str(_lineage_p)
                if str(_lineage_p) not in artifact_list:
                    artifact_list.append(str(_lineage_p))
        except Exception as exc:
            du.print_warning(f"[LINEAGE] Sample stage lineage export skipped: {exc}")
        feat_cols_post = getattr(app_config, "RUNTIME_TRAINING_FINAL_FEATURE_COLUMNS", None)
        manifest_context["feature_matrix_cols_post_prune"] = feat_cols_post
        manifest_context["trained_model_count"] = int(
            len(model_results) if isinstance(model_results, dict) else 0
        )

        aligned_n_obs = manifest_context.get("aligned_supervised_rows")
        post_ls_obs = manifest_context.get("post_low_support_training_rows")
        feats_after_obs = manifest_context.get("feature_matrix_cols_post_prune")
        feats_before_obs = manifest_context.get("_aligned_feature_cols")
        tr_split = manifest_context.get("train_sample_count")
        te_split = manifest_context.get("test_sample_count")
        try:
            pool_for_split = int(post_ls_obs) if post_ls_obs not in (None, "") else None
        except Exception:
            pool_for_split = None
        try:
            tr_i = int(tr_split) if tr_split not in (None, "") else None
        except Exception:
            tr_i = None
        try:
            te_i = int(te_split) if te_split not in (None, "") else None
        except Exception:
            te_i = None
        if tr_i is not None or te_i is not None:
            obs_api.record_training_split_allocation(
                manifest_context,
                pool_rows=pool_for_split,
                train_rows=tr_i,
                test_rows=te_i,
                reason="train/test split from RUNTIME_SPLIT_METADATA (post low-support mask)",
                artifact_path=split_audit_path_str,
            )
        obs_tr = manifest_context.get("pipeline_observability")
        if isinstance(obs_tr, PipelineObservabilitySession):
            try:
                if aligned_n_obs is not None and post_ls_obs is not None:
                    obs_tr.log_population_transition(
                        transition="aligned_supervised_to_post_low_support_training",
                        previous_count=int(aligned_n_obs),
                        new_count=int(post_ls_obs),
                        reason="RUNTIME_POST_LOW_SUPPORT_TRAINING_ROWS min-family/support mask",
                        artifact_path=str(Path(DIAGNOSTICS_DIR) / f"split_freeze_audit_{run_id}.csv"),
                    )
            except Exception:
                pass
            try:
                if feats_before_obs is not None and feats_after_obs is not None:
                    obs_tr.log_schema_change(
                        stage_hint="training_stage_pruned_feature_matrix",
                        previous_cols=int(feats_before_obs),
                        new_cols=int(feats_after_obs),
                        reason="trainer contract / leakage prune / variance filters (see modality contract CSV)",
                        artifact_path=str(Path(DIAGNOSTICS_DIR) / f"feature_contract_{run_id}.json"),
                    )
            except Exception:
                pass
        mw_train: list[str] = []
        if bool(manifest_context.get("permission_enrichment_degraded")):
            mw_train.append("permission enrichment degraded flag set")
        tr_c = manifest_context.get("train_sample_count")
        te_c = manifest_context.get("test_sample_count")
        if tr_c not in (None, "") or te_c not in (None, ""):
            mw_train.append(f"split train={tr_c} test={te_c}")
        _record_stage_timing(
            "training",
            stage_started_at,
            input_rows=aligned_n_obs,
            output_rows=post_ls_obs,
            input_features=feats_before_obs,
            output_features=feats_after_obs,
            major_warnings="; ".join(mw_train) if mw_train else "",
        )
        pop_line = _format_population_pipeline_summary_line(manifest_context)
        if pop_line:
            manifest_context["population_pipeline_summary_line"] = pop_line
            du.print_info(f"[POPULATION] {pop_line}")

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
                pipeline_results=pipeline_results,
                manifest_context=manifest_context,
            )
            manifest_context["_ablation_run_status_summary"] = (
                f"PASS artifact_paths={len(ablation_artifacts)} (see ablation_summary_{run_id}.csv)"
            )
            summ = Path(DIAGNOSTICS_DIR) / f"ablation_summary_{run_id}.csv"
            if not summ.exists():
                summ = Path(DIAGNOSTICS_DIR) / "ablation_summary.latest.csv"
            obs_ab = manifest_context.get("pipeline_observability")
            if isinstance(obs_ab, PipelineObservabilitySession):
                obs_ab.emit_jsonl(
                    LogCategory.ABLATION_STATUS,
                    severity=LogSeverity.INFO,
                    message="ablation_complete",
                    ablation_summary_path=str(summ),
                )
            _record_stage_timing(
                "ablation",
                stage_started_at,
                artifacts_written_count=str(len(ablation_artifacts)),
                major_warnings=(
                    "Multi-label experimental targets enabled; compare label_target rows in ablation summary."
                    if bool(getattr(app_config, "ENABLE_ABLATION_MULTI_LABEL_TARGETS", True))
                    else ""
                ),
                extras={"ablation_summary_path": str(summ)},
            )
            for artifact_path in ablation_artifacts:
                if artifact_path not in artifact_list:
                    artifact_list.append(artifact_path)
        elif run_ablation_flag and skip_ablation_for_single_model and model_list and len(model_list) == 1:
            manifest_context["_ablation_run_status_summary"] = "SKIPPED (SKIP_ABLATIONS_FOR_SINGLE_MODEL policy)"
            du.print_info(
                "[ABLATION] Skipped for single-model run "
                "(set SKIP_ABLATIONS_FOR_SINGLE_MODEL=False to force)."
            )
            obs_sk = manifest_context.get("pipeline_observability")
            if isinstance(obs_sk, PipelineObservabilitySession):
                obs_sk.emit_stage_completion(
                    "ablation",
                    status="SKIPPED",
                    duration_sec=0.0,
                    major_warnings="SKIP_ABLATIONS_FOR_SINGLE_MODEL=True with single-model list",
                    next_stage_allowed=True,
                    extras={"policy": "SKIP_ABLATIONS_FOR_SINGLE_MODEL"},
                )
        elif not run_ablation_flag:
            manifest_context["_ablation_run_status_summary"] = "DISABLED (ENABLE_ABLATION_EXPERIMENTS=False)"
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
            _record_stage_timing(
                "permission_trends",
                stage_started_at,
                artifacts_written_count=str(len(report_artifacts)),
            )
            for artifact_path in report_artifacts:
                if artifact_path not in artifact_list:
                    artifact_list.append(artifact_path)
            if stop_after == "permission_trends":
                _mark_run_state("partial", completed_stage="permission_trends")
                du.print_success("[PIPELINE] Stopped after permission trends stage by request.")
                return _finalize_with_manifest_timing()
        else:
            obs_pt = manifest_context.get("pipeline_observability")
            if isinstance(obs_pt, PipelineObservabilitySession):
                obs_pt.emit_stage_completion(
                    "permission_trends",
                    status="SKIPPED",
                    duration_sec=0.0,
                    major_warnings="ENABLE_PERMISSION_TRENDS_REPORT=False",
                    next_stage_allowed=True,
                    extras={"reason": "permission_trends_disabled"},
                )
            if stop_after == "permission_trends":
                _mark_run_state("partial", completed_stage="ablation")
                du.print_warning(
                    "[PIPELINE] stop_after='permission_trends' requested but "
                    "permission trends are disabled; stopping after ablation/training."
                )
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
            df_labels = resolve_final_labels_stage(vendor_records, model_results)
            lbl_n = len(df_labels) if df_labels is not None else 0
            _record_stage_timing("label_resolution", stage_started_at, output_rows=lbl_n)
            if df_labels is not None:
                du.print_info(f"[PIPELINE] Final labels generated: {len(df_labels)} samples")
                tax_sum = getattr(app_config, "RUNTIME_TAXONOMY_CONSISTENCY_SUMMARY", None)
                if isinstance(tax_sum, dict):
                    manifest_context["taxonomy_consistency_summary"] = tax_sum
                    tpath = tax_sum.get("mismatch_csv_path")
                    if tpath:
                        manifest_context["taxonomy_mismatch_csv"] = str(tpath)
                        if str(tpath) not in artifact_list:
                            artifact_list.append(str(tpath))
                    pex = tax_sum.get("paper_taxonomy_excluded_sample_ids_path")
                    if pex:
                        manifest_context["paper_taxonomy_excluded_sample_ids_json"] = str(pex)
                        if str(pex) not in artifact_list:
                            artifact_list.append(str(pex))
        else:
            du.print_info("[PIPELINE] Label resolution stage disabled by configuration.")
            obs_lr = manifest_context.get("pipeline_observability")
            if isinstance(obs_lr, PipelineObservabilitySession):
                obs_lr.emit_stage_completion(
                    "label_resolution",
                    status="SKIPPED",
                    duration_sec=0.0,
                    major_warnings="ENABLE_LABEL_RESOLUTION_STAGE=False",
                    next_stage_allowed=True,
                    extras={"reason": "label_resolution_disabled"},
                )

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
        obs_ex = manifest_context.get("pipeline_observability")
        if isinstance(obs_ex, PipelineObservabilitySession):
            fatalish = isinstance(e, _PipelineStageFailure)
            obs_ex.record_partial_failure(
                stage=str(current_stage_name or manifest_context.get("current_stage") or "unknown"),
                error=error_text,
                recoverable=fatalish,
            )
            if not fatalish:
                obs_ex.add_warning(error_text[:2000], severity=LogSeverity.ERROR, stage_hint=str(current_stage_name))
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
        from_main_or("runtime_logging", runtime_logging).stop_runtime_logging(runtime_log_context)
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
        clear_pipeline_run_bounds()
        _set_diagnostics_dir(original_diagnostics_dir)
