"""Pipeline orchestration: profile loading, staged execution, manifest finalization.

Canonical implementation (**Pass 67**): lives under ``obsidiandroid.pipeline.runner``.
``analysis.pipeline.runner`` is a thin ``sys.modules`` identity shim.

This module holds ``run_pipeline`` and run-scoped helpers extracted from ``main.py``
so the CLI entry module stays thin and tests can import ``main.run_pipeline`` unchanged.
"""

import os
import traceback
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Sequence, Any
from time import perf_counter

import pandas as pd

from config import app_config
from obsidiandroid.modeling.model_trainer_factory import reset_runtime_training_caches

# === Database + Utilities ===
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import ml_console
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.common.run_lifecycle import mark_run_lifecycle_running
from obsidiandroid.reporting import family_distribution_report
import obsidiandroid.cli.profile_manager as profile_manager
import obsidiandroid.governance.run_manifest as run_manifest
from obsidiandroid.governance import evidence_mode_resolver
from obsidiandroid.observability.logging import runtime as runtime_logging
from obsidiandroid.observability.logging import logger as logger_manager
from obsidiandroid.observability.logging import get_logger, log_event
from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.diagnostics import cohort_foundation_export
from obsidiandroid.diagnostics import cohort_sample_id_audit
from obsidiandroid.diagnostics import cohort_vocabulary
from obsidiandroid.diagnostics import feature_build_coverage_export
from obsidiandroid.diagnostics import fused_permission_matrix_audit
from obsidiandroid.diagnostics import permission_training_survival_audit

# === Analysis Pipelines (staged pipeline) ===
from obsidiandroid.pipeline.stage_av_vendor import (
    extract_vendor_metadata_stage,
    run_av_analysis_stage,
    run_feature_alignment_stage,
)
from obsidiandroid.pipeline.stage_samples import load_and_prepare_samples
from obsidiandroid.pipeline.stage_feature_enrichment import merge_sample_metadata_features
from obsidiandroid.pipeline.stage_feature_enrichment import build_permission_enrichment_frame
from obsidiandroid.pipeline.stage_ablation import run_ablation_experiments
from obsidiandroid.pipeline.stage_permission_trends_report import run_permission_trends_report_stage
from obsidiandroid.pipeline.stage_modeling import (
    build_feature_matrix_stage,
    compute_engine_weights_from_pipeline,
    resolve_final_labels_stage,
    run_training_stage,
)
from obsidiandroid.pipeline.runtime_policy import (
    apply_profile_runtime_policy,
    build_mutable_config_keys,
    clear_cross_run_artifact_path_pointers,
    enforce_paper_perturbation_axes as enforce_paper_perturbation_axes_policy,
    reset_runtime_markers,
)
from obsidiandroid.orchestration.methodology_artifacts import (
    export_feature_contract,
    export_leakage_assessment,
    export_modality_method_contract,
)
from obsidiandroid.orchestration.runtime_reporting import (
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
from obsidiandroid.pipeline.main_facade import from_main_or
from obsidiandroid.pipeline.runner_support import (
    PipelineStageFailure,
    ScopedArtifactList,
    sync_main_module_diagnostics,
)
from obsidiandroid.pipeline.runner_stage_control import PipelineRunStageControl
from obsidiandroid.pipeline.run_bounds import (
    PipelineRunBounds,
    clear_pipeline_run_bounds,
    set_pipeline_run_bounds,
)
from obsidiandroid.observability.pipeline_observability import PipelineObservabilitySession
from obsidiandroid.observability.pipeline_observability import api as obs_api
from obsidiandroid.observability.pipeline_observability.taxonomy import LogCategory, LogSeverity
import obsidiandroid.reporting.operator_dashboard as operator_dashboard

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


def _set_diagnostics_dir(path: str) -> None:
    """Update runner global diagnostics dir and keep ``main.DIAGNOSTICS_DIR`` in sync."""
    global DIAGNOSTICS_DIR
    DIAGNOSTICS_DIR = path
    sync_main_module_diagnostics(path)


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
    artifact_list: ScopedArtifactList = ScopedArtifactList(
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
    original_diagnostics_dir = DIAGNOSTICS_DIR
    # Reset run-scoped runtime markers up-front to avoid stale cross-run leakage.
    reset_runtime_markers()
    operator_dashboard.clear_operator_state()
    st = PipelineRunStageControl(
        run_id=run_id,
        stop_after=stop_after,
        manifest_context=manifest_context,
        artifact_list=artifact_list,
        pipeline_started_at=pipeline_started_at,
        diagnostics_dir_getter=lambda: DIAGNOSTICS_DIR,
        pipeline_logger=PIPELINE_MAIN_LOGGER,
    )

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
        rr = str(runtime_run_root or "").strip()
        if rr:
            mark_run_lifecycle_running(Path(rr))
            manifest_context["lifecycle_started_at_utc"] = datetime.now(timezone.utc).isoformat()

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
        st.write_preflight(status="running")

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
        if bool(getattr(app_config, "EVIDENCE_MODE_ENABLED", getattr(app_config, "PAPER_MODE_ENABLED", False))):
            runtime_overrides = profile.get("runtime_overrides", {}) if isinstance(profile, dict) else {}
            if (
                not isinstance(runtime_overrides, dict)
                or "WRITE_RUN_SCOPED_PERMISSION_TREND_ARTIFACTS" not in runtime_overrides
            ):
                setattr(app_config, "WRITE_RUN_SCOPED_PERMISSION_TREND_ARTIFACTS", True)
        if bool(getattr(app_config, "EVIDENCE_MODE_ENABLED", getattr(app_config, "PAPER_MODE_ENABLED", False))) and bool(
            getattr(app_config, "ENABLE_DYNAMIC_GENERIC_VENDOR_PARSERS", True)
        ):
            st.fail_pipeline(
                "[EVIDENCE] Dynamic generic vendor onboarding must be disabled in evidence mode.",
                stage_name="preflight",
            )

        preflight_perf = perf_counter()
        st.begin_stage("preflight")

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
        st.begin_stage("samples")
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
        st.record_stage_timing(
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
            st.mark_run_state("partial", completed_stage="samples")
            st.write_preflight(
                status="stopped_after_samples",
                reason="stop_after=samples (cohort audit; later stages skipped)",
            )
            du.print_success("[PIPELINE] Stopped after sample preparation by request.")
            pipeline_results = None
            vendor_eval = None
            return st.finalize_with_manifest_timing(
                profile=profile,
                samples_df=samples_df,
                pipeline_results=pipeline_results,
                vendor_eval=vendor_eval,
            )

        # Step 2: Run AV engine pipeline
        stage_started_at = perf_counter()
        st.begin_stage("av_pipeline")
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
            st.record_stage_timing(
                "av_pipeline",
                stage_started_at,
                stage_status="FAIL",
                input_rows=int(len(samples_df)),
                major_warnings="av_pipeline_returned_empty",
            )
            st.fail_pipeline("[PIPELINE] AV pipeline returned no results.")
        # Summaries measure cohort rows consistently: engine_scores often has one row per engine
        # (no sample_id); avoid reporting that as ``output_rows`` in pipeline_stage_summary.
        eng_preview = pipeline_results.get("engine_scores") if isinstance(pipeline_results, dict) else None
        av_summary_extras: dict[str, Any] = {}
        if isinstance(eng_preview, pd.DataFrame) and not eng_preview.empty:
            av_summary_extras["engine_scores_table_rows"] = int(len(eng_preview))
            if "sample_id" in eng_preview.columns:
                av_summary_extras["engine_scores_distinct_samples"] = int(
                    eng_preview["sample_id"].nunique(dropna=True)
                )
        st.record_stage_timing(
            "av_pipeline",
            stage_started_at,
            input_rows=int(len(samples_df)),
            output_rows=int(len(samples_df)),
            major_warnings="",
            extras=av_summary_extras,
        )
        eng_overlay_csv = str(getattr(app_config, "RUNTIME_ENGINE_METADATA_OVERLAY_CSV", "") or "").strip()
        if eng_overlay_csv:
            manifest_context["engine_metadata_overlay_csv"] = eng_overlay_csv
            if eng_overlay_csv not in artifact_list:
                artifact_list.append(eng_overlay_csv)

        if stop_after == "av_pipeline":
            st.mark_run_state("partial", completed_stage="av_pipeline")
            du.print_success("[PIPELINE] Stopped after AV pipeline by request.")
            vendor_eval = None
            return st.finalize_with_manifest_timing(
                profile=profile,
                samples_df=samples_df,
                pipeline_results=pipeline_results,
                vendor_eval=vendor_eval,
            )

        # Step 3: Extract vendor metadata
        stage_started_at = perf_counter()
        st.begin_stage("vendor_metadata")
        _print_run_context_line(
            run_id=run_id,
            profile_id=profile_id,
            stage="vendor_metadata",
            stop_after=stop_after,
            selected_models=model_list,
        )
        vendor_eval, vendor_records, parsed_data, _scorecard_df = extract_vendor_metadata_stage(
            pipeline_results=pipeline_results,
            samples_df=samples_df,
        )
        st.record_stage_timing("vendor_metadata", stage_started_at)
        if vendor_eval is None:
            st.fail_pipeline("[PIPELINE] Vendor metadata extraction returned no evaluation frame.")

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
            st.mark_run_state("partial", completed_stage="vendor_metadata")
            du.print_success("[PIPELINE] Stopped after vendor metadata by request.")
            return st.finalize_with_manifest_timing(
                profile=profile,
                samples_df=samples_df,
                pipeline_results=pipeline_results,
                vendor_eval=vendor_eval,
            )

        # Step 4: Compute engine weights
        stage_started_at = perf_counter()
        st.begin_stage("engine_weights")
        _print_run_context_line(
            run_id=run_id,
            profile_id=profile_id,
            stage="engine_weights",
            stop_after=stop_after,
            selected_models=model_list,
        )
        weights_df = compute_engine_weights_from_pipeline(pipeline_results)
        st.record_stage_timing(
            "engine_weights",
            stage_started_at,
            output_rows=int(len(weights_df)) if weights_df is not None else "",
        )
        if weights_df is None or weights_df.empty:
            st.fail_pipeline("[PIPELINE] Engine weight computation failed.")
        pipeline_results["weights_df"] = weights_df

        if stop_after == "engine_weights":
            st.mark_run_state("partial", completed_stage="engine_weights")
            du.print_success("[PIPELINE] Stopped after engine scoring by request.")
            return st.finalize_with_manifest_timing(
                profile=profile,
                samples_df=samples_df,
                pipeline_results=pipeline_results,
                vendor_eval=vendor_eval,
            )

        # Step 5: Print family distribution
        if bool(getattr(app_config, "ENABLE_FAMILY_DISTRIBUTION_REPORT", True)):
            family_distribution_report.print_family_distribution_stats(samples_df)
        else:
            du.print_info("[PIPELINE] Family distribution report disabled by configuration.")

        # Step 6: Build feature matrix (+ optional metadata features)
        stage_started_at = perf_counter()
        st.begin_stage("feature_matrix")
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
            st.fail_pipeline("[PIPELINE] Feature matrix generation failed.")
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
        st.record_stage_timing(
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
            min_selected = safe_int_config_value(
                getattr(app_config, "FEATURE_MIN_SELECTED_VENDORS", 1),
                default=1,
            )
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
                row_n = fused_perm_sig.get("fused_matrix_row_count")
                any_perm = fused_perm_sig.get("fused_matrix_rows_with_any_perm_like_positive")
                pi_like = fused_perm_sig.get("fused_matrix_perm_like_column_count")
                du.print_subheader("Fused ML matrix — permission slice")
                du.print_info(
                    "  rows={rows} | cols≈perm_family {pcols} | "
                    "rows_with_any_perm_signal={psig}".format(
                        rows=row_n,
                        pcols=pi_like,
                        psig=any_perm,
                    )
                )
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
                            operator_dashboard.record_operator_issue(
                                tag="COVERAGE",
                                title="Enrichment vs fused row authority mismatch risk",
                                lines=[
                                    (
                                        f"Cohort_n={cohort_i} fused_rows={fused_i} (Δ={gap}); "
                                        f"enrichment permission-bag positives≈{int(enrich_any)}, "
                                        f"fused perm-signal rows={int(fused_any)}."
                                    ),
                                    "See feature_build_coverage + permission_fuse_audit JSON for detail.",
                                ],
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

        gov_notes: list[str] = []
        if bool(getattr(app_config, "ENABLE_FEATURE_CONTRACT_EXPORT", True)):
            feature_contract_path = export_feature_contract(
                feature_df=feature_df,
                run_id=run_id,
                output_dir=DIAGNOSTICS_DIR,
            )
            if feature_contract_path:
                artifact_list.append(feature_contract_path)
                operator_dashboard.bump_artifact_counter("diagnostics", 1)
                gov_notes.append(f"feature_contract={Path(feature_contract_path).name}")

        if bool(getattr(app_config, "ENABLE_LEAKAGE_ASSESSMENT_EXPORT", True)):
            leakage_path = export_leakage_assessment(
                feature_df=feature_df,
                run_id=run_id,
                output_dir=DIAGNOSTICS_DIR,
            )
            if leakage_path:
                artifact_list.append(leakage_path)
                operator_dashboard.bump_artifact_counter("diagnostics", 1)
                gov_notes.append(f"leakage={Path(leakage_path).name}")
        modality_contract_path = export_modality_method_contract(
            permission_df=permission_features_df,
            fusion_feature_df=feature_df,
            run_id=run_id,
            output_dir=DIAGNOSTICS_DIR,
        )
        if modality_contract_path:
            artifact_list.append(modality_contract_path)
            operator_dashboard.bump_artifact_counter("diagnostics", 1)
            gov_notes.append(f"modality_contract={Path(modality_contract_path).name}")
        if gov_notes:
            du.print_info("[ARTIFACTS] Governance / contracts: " + " | ".join(gov_notes))

        if stop_after == "feature_matrix":
            st.mark_run_state("partial", completed_stage="feature_matrix")
            du.print_success("[PIPELINE] Stopped after feature matrix build by request.")
            return st.finalize_with_manifest_timing(
                profile=profile,
                samples_df=samples_df,
                pipeline_results=pipeline_results,
                vendor_eval=vendor_eval,
            )

        # Step 7: Align features and labels
        stage_started_at = perf_counter()
        st.begin_stage("alignment")
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
            st.fail_pipeline("[PIPELINE] Feature-label alignment failed.")
        manifest_context["aligned_supervised_rows"] = int(len(aligned_feature_df))
        manifest_context["_aligned_feature_cols"] = int(aligned_feature_df.shape[1])
        obs_al = manifest_context.get("pipeline_observability")
        if isinstance(obs_al, PipelineObservabilitySession):
            split_audit_guess = str(Path(DIAGNOSTICS_DIR) / f"split_freeze_headline_{run_id}.csv")
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
            artifact_path=str(Path(DIAGNOSTICS_DIR) / f"split_freeze_headline_{run_id}.csv"),
        )
        st.record_stage_timing(
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
            st.mark_run_state("partial", completed_stage="alignment")
            du.print_success("[PIPELINE] Stopped after feature-label alignment by request.")
            return st.finalize_with_manifest_timing(
                profile=profile,
                samples_df=samples_df,
                pipeline_results=pipeline_results,
                vendor_eval=vendor_eval,
            )

        # Step 8: Train classifiers
        stage_started_at = perf_counter()
        model_list = model_list or list(profile.get("model_list", []))
        st.begin_stage("training")
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
            st.fail_pipeline("[PIPELINE] Model training returned no results.")
        if isinstance(model_results, dict) and model_results:
            pipeline_results.update(model_results)
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
        headline_split = getattr(app_config, "RUNTIME_HEADLINE_SPLIT_METADATA", None)
        split_meta = (
            headline_split
            if isinstance(headline_split, dict) and headline_split.get("split_audit_path")
            else getattr(app_config, "RUNTIME_SPLIT_METADATA", None)
        )
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
        manifest_context["label_authority"] = {
            "training_label_field": str(
                getattr(app_config, "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD", "") or "family_id"
            ),
            "display_label_field": "family_canonical",
            "label_selection_policy": "family_id_first",
            "active_training_classes": getattr(
                app_config, "RUNTIME_TRAINING_LABEL_CLASS_COUNT", None
            ),
            "cohort_family_count": safe_int_config_value(
                getattr(app_config, "RUNTIME_COHORT_FAMILY_COUNT", 0),
                default=0,
            )
        }
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
                        artifact_path=str(Path(DIAGNOSTICS_DIR) / f"split_freeze_headline_{run_id}.csv"),
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
        st.record_stage_timing(
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
            st.mark_run_state("partial", completed_stage="training")
            _apply_confusion_matrix_policy(run_id=run_id, top_model=top_model_for_policy)
            du.print_success("[PIPELINE] Stopped after model training by request.")
            return st.finalize_with_manifest_timing(
                profile=profile,
                samples_df=samples_df,
                pipeline_results=pipeline_results,
                vendor_eval=vendor_eval,
            )

        run_ablation_flag = bool(getattr(app_config, "ENABLE_ABLATION_EXPERIMENTS", False))
        skip_ablation_for_single_model = bool(
            getattr(app_config, "SKIP_ABLATIONS_FOR_SINGLE_MODEL", True)
        )
        if (
            run_ablation_flag
            and not (skip_ablation_for_single_model and model_list and len(model_list) == 1)
        ):
            stage_started_at = perf_counter()
            st.begin_stage("ablation")
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
            outcome_path = Path(DIAGNOSTICS_DIR) / f"ablation_run_outcome_{run_id}.json"
            outcome_status = "complete"
            if outcome_path.is_file():
                try:
                    oc_payload = json.loads(outcome_path.read_text(encoding="utf-8"))
                    outcome_status = str(oc_payload.get("ablation_grid_status") or "complete").strip().lower()
                except Exception:
                    outcome_status = "complete"
            summ = Path(DIAGNOSTICS_DIR) / f"ablation_summary_{run_id}.csv"
            if not summ.is_file():
                alt_partial = Path(DIAGNOSTICS_DIR) / f"ablation_summary_partial_{run_id}.csv"
                if alt_partial.is_file():
                    summ = alt_partial
                else:
                    summ = Path(DIAGNOSTICS_DIR) / "ablation_summary.latest.csv"
            manifest_context["_ablation_run_status_summary"] = (
                f"artifact_paths={len(ablation_artifacts)} ablation_grid_status={outcome_status} "
                f"summary={summ.name}"
            )
            obs_ab = manifest_context.get("pipeline_observability")
            if isinstance(obs_ab, PipelineObservabilitySession):
                obs_ab.emit_jsonl(
                    LogCategory.ABLATION_STATUS,
                    severity=LogSeverity.INFO,
                    message="ablation_complete" if outcome_status == "complete" else "ablation_outcome",
                    ablation_summary_path=str(summ),
                    ablation_grid_status=str(outcome_status),
                )
            st.record_stage_timing(
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
            st.mark_run_state("partial", completed_stage="ablation")
            du.print_success("[PIPELINE] Stopped after ablation stage by request.")
            return st.finalize_with_manifest_timing(
                profile=profile,
                samples_df=samples_df,
                pipeline_results=pipeline_results,
                vendor_eval=vendor_eval,
            )

        permission_trends_enabled = bool(getattr(app_config, "ENABLE_PERMISSION_TRENDS_REPORT", True))
        if permission_trends_enabled:
            stage_started_at = perf_counter()
            st.begin_stage("permission_trends")
            report_artifacts = run_permission_trends_report_stage(
                samples_df=samples_df,
                permission_features_df=permission_features_df,
                parsed_data=parsed_data,
                model_results=model_results,
                run_id=run_id,
                profile_id=profile_id,
                feature_df=feature_df,
            )
            st.record_stage_timing(
                "permission_trends",
                stage_started_at,
                artifacts_written_count=str(len(report_artifacts)),
            )
            for artifact_path in report_artifacts:
                if artifact_path not in artifact_list:
                    artifact_list.append(artifact_path)
            if stop_after == "permission_trends":
                st.mark_run_state("partial", completed_stage="permission_trends")
                du.print_success("[PIPELINE] Stopped after permission trends stage by request.")
                return st.finalize_with_manifest_timing(
                    profile=profile,
                    samples_df=samples_df,
                    pipeline_results=pipeline_results,
                    vendor_eval=vendor_eval,
                )
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
                st.mark_run_state("partial", completed_stage="ablation")
                du.print_warning(
                    "[PIPELINE] stop_after='permission_trends' requested but "
                    "permission trends are disabled; stopping after ablation/training."
                )
                return st.finalize_with_manifest_timing(
                    profile=profile,
                    samples_df=samples_df,
                    pipeline_results=pipeline_results,
                    vendor_eval=vendor_eval,
                )

        # Step 9: Final label resolution
        label_resolution_enabled = bool(getattr(app_config, "ENABLE_LABEL_RESOLUTION_STAGE", True))
        if label_resolution_enabled:
            stage_started_at = perf_counter()
            st.begin_stage("label_resolution")
            _print_run_context_line(
                run_id=run_id,
                profile_id=profile_id,
                stage="label_resolution",
                stop_after=stop_after,
                selected_models=model_list,
            )
            df_labels = resolve_final_labels_stage(vendor_records, model_results)
            lbl_n = len(df_labels) if df_labels is not None else 0
            st.record_stage_timing("label_resolution", stage_started_at, output_rows=lbl_n)
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
            st.mark_run_state(
                "partial",
                completed_stage="label_resolution" if label_resolution_enabled else "permission_trends",
            )
            if not label_resolution_enabled:
                du.print_warning(
                    "[PIPELINE] stop_after='label_resolution' requested, but the stage is disabled."
                )
            du.print_success("[PIPELINE] Stopped after final label resolution by request.")
            return st.finalize_with_manifest_timing(
                profile=profile,
                samples_df=samples_df,
                pipeline_results=pipeline_results,
                vendor_eval=vendor_eval,
            )

        total_runtime_sec = max(0.0, perf_counter() - pipeline_started_at)
        du.print_info(f"[TIME] total_pipeline_runtime: {total_runtime_sec:.2f}s")
        log_event(
            PIPELINE_MAIN_LOGGER,
            "pipeline_timing_complete",
            run_id=run_id,
            total_runtime_sec=round(total_runtime_sec, 2),
            stages={k: round(v, 2) for k, v in st.stage_timings_sec.items()},
        )
        st.attach_runtime_timing_context()
        run_summary_payload = _build_run_summary_payload(
            run_id=run_id,
            profile_id=profile_id,
            samples_df=samples_df,
            model_results=model_results if isinstance(model_results, dict) else {},
            top_model=top_model_for_policy,
            manifest_context=manifest_context,
        )
        diag_path = Path(str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", DIAGNOSTICS_DIR) or DIAGNOSTICS_DIR))
        _export_and_print_run_summary(
            payload=run_summary_payload,
            artifact_list=artifact_list,
            echo_terminal=False,
        )
        operator_dashboard.emit_research_operator_report(
            diagnostics_dir=diag_path,
            run_id=run_id,
            profile_id=profile_id,
            manifest_context=manifest_context,
            samples_df=samples_df if isinstance(samples_df, pd.DataFrame) else None,
            model_results=model_results if isinstance(model_results, dict) else {},
            top_model=top_model_for_policy,
            artifact_list=list(artifact_list),
        )
        du.print_success("Classification pipeline executed successfully.")
        st.mark_run_state("complete", completed_stage="manifest")
        st.write_preflight(status="pass")
        return st.finalize_with_manifest_timing(
            profile=profile,
            samples_df=samples_df,
            pipeline_results=pipeline_results,
            vendor_eval=vendor_eval,
        )

    except KeyboardInterrupt:
        du.print_warning(
            "[PIPELINE] KeyboardInterrupt — recording interrupted stage, then finalizing run manifest "
            "(partial ablation artifacts may exist under diagnostics/)."
        )
        if st.current_stage_name and st.active_perf_stage_start is not None:
            st.record_stage_timing(
                str(st.current_stage_name),
                st.active_perf_stage_start,
                stage_status="INTERRUPTED",
                next_stage_allowed=False,
                major_warnings="KeyboardInterrupt (operator or session)",
            )
        st.mark_run_state(
            "interrupted",
            failure_reason="KeyboardInterrupt",
            failed_stage=str(st.current_stage_name or "") or "unknown",
        )
        st.write_preflight(status="interrupted", reason="KeyboardInterrupt")
        try:
            st.attach_runtime_timing_context()
        except Exception:
            pass
        if manifest_context.get("run_id"):
            try:
                st.finalize_with_manifest_timing(
                    profile=profile,
                    samples_df=samples_df,
                    pipeline_results=pipeline_results,
                    vendor_eval=vendor_eval,
                )
            except Exception as fin_exc:
                du.print_warning(f"[PIPELINE] Manifest finalization after interrupt failed: {fin_exc}")
        return 130

    except Exception as e:
        error_text = str(e)
        obs_ex = manifest_context.get("pipeline_observability")
        if isinstance(obs_ex, PipelineObservabilitySession):
            fatalish = isinstance(e, PipelineStageFailure)
            obs_ex.record_partial_failure(
                stage=str(st.current_stage_name or manifest_context.get("current_stage") or "unknown"),
                error=error_text,
                recoverable=fatalish,
            )
            if not fatalish:
                obs_ex.add_warning(error_text[:2000], severity=LogSeverity.ERROR, stage_hint=str(st.current_stage_name))
        if (
            st.current_stage_name == "ablation"
            and st.active_perf_stage_start is not None
            and st.last_completed_stage != "ablation"
        ):
            st.record_stage_timing(
                "ablation",
                st.active_perf_stage_start,
                stage_status="FAIL",
                next_stage_allowed=False,
                major_warnings=error_text[:900],
            )
        if error_text.startswith("[INTEGRITY]"):
            du.print_error("[INTEGRITY STOP]")
        else:
            du.print_error(f"[CRITICAL] Pipeline crashed: {e}")
        st.mark_run_state(
            "failed",
            failure_reason=error_text,
            failed_stage=st.current_stage_name or st.last_completed_stage,
        )
        if st.current_stage_name == "ablation":
            manifest_context["_ablation_run_status_summary"] = f"FAIL: {error_text[:400]}"
        st.write_preflight(status="failed", reason=str(e))
        manifest_context["integrity_error"] = error_text

        # Avoid full tracebacks for expected profile/data failures
        if ml_console.is_debug() and not error_text.startswith("[PROFILE]") and not isinstance(e, PipelineStageFailure):
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
            st.finalize_with_manifest_timing(
                profile=profile,
                samples_df=samples_df,
                pipeline_results=pipeline_results,
                vendor_eval=vendor_eval,
            )
        if bool(getattr(app_config, "EVIDENCE_MODE_ENABLED", getattr(app_config, "PAPER_MODE_ENABLED", False))) and bool(
            getattr(
                app_config,
                "FAIL_FAST_PIPELINE_EXCEPTIONS_IN_EVIDENCE_MODE",
                getattr(app_config, "FAIL_FAST_PIPELINE_EXCEPTIONS_IN_PAPER_MODE", True),
            )
        ) and not error_text.startswith("[INTEGRITY]") and not error_text.startswith("[PROFILE]") and not isinstance(
            e, PipelineStageFailure
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
