"""Run-scoped pipeline stage timing, preflight, and manifest finalization helpers.

Extracted from ``runner.run_pipeline`` so the orchestration body stays readable.
State (current stage, timings, preflight paths) lives on ``PipelineRunStageControl``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.run_lifecycle import finalize_run_lifecycle_terminal, touch_run_lifecycle_running
from obsidiandroid.diagnostics import cohort_vocabulary
from obsidiandroid.observability.logging import log_event
from obsidiandroid.observability.pipeline_observability import PipelineObservabilitySession
from obsidiandroid.cli.main_override_bridge import resolve_main_override
from obsidiandroid.pipeline.manifest.stage_manifest_writers import merge_lifecycle_fields_into_run_summaries
from obsidiandroid.pipeline.runner_support import PipelineStageFailure, ScopedArtifactList
from obsidiandroid.pipeline.stage_manifest import finalize_run_manifest_stage


class PipelineRunStageControl:
    """Mutable per-run state and helpers for stage transitions and finalization."""

    def __init__(
        self,
        *,
        run_id: str,
        stop_after: str,
        manifest_context: dict[str, Any],
        artifact_list: ScopedArtifactList,
        pipeline_started_at: float,
        diagnostics_dir_getter: Callable[[], str],
        pipeline_logger: Any,
    ) -> None:
        self.run_id = run_id
        self.stop_after = stop_after
        self.manifest_context = manifest_context
        self.artifact_list = artifact_list
        self.pipeline_started_at = pipeline_started_at
        self._diagnostics_dir_getter = diagnostics_dir_getter
        self._pipeline_logger = pipeline_logger
        self.stage_timings_sec: dict[str, float] = {}
        self.current_stage_name: str | None = None
        self.active_perf_stage_start: float | None = None
        self.last_completed_stage: str | None = None
        self.preflight_path: Path | None = None
        self.preflight_payload: dict[str, Any] = {}

    def record_stage_timing(
        self,
        stage_name: str,
        started_at: float,
        *,
        record_observability: bool = True,
        **obs_kwargs: Any,
    ) -> None:
        duration = max(0.0, perf_counter() - started_at)
        self.stage_timings_sec[stage_name] = duration
        self.last_completed_stage = stage_name
        self.manifest_context["completed_stage"] = stage_name
        display_stage_name = "manifest stage total" if str(stage_name).strip().lower() == "manifest" else stage_name
        du.print_info(f"[TIME] {display_stage_name}: {du.format_elapsed_duration(duration)}")
        log_event(
            self._pipeline_logger,
            "stage_timing",
            event_id="PIPE_STAGE_200",
            run_id=self.run_id,
            stage=stage_name,
            duration_sec=round(duration, 2),
        )
        if not record_observability:
            return
        obs_sess = self.manifest_context.get("pipeline_observability")
        if isinstance(obs_sess, PipelineObservabilitySession):
            obs_copy = dict(obs_kwargs)
            wall_start = str(self.manifest_context.pop("_active_stage_wall_start_iso", "") or "").strip()
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

    def mark_run_state(
        self,
        status: str,
        *,
        completed_stage: str | None = None,
        failure_reason: str = "",
        failed_stage: str | None = None,
    ) -> None:
        """Persist concise run-state metadata for final summary and manifest export."""
        normalized_status = str(status).strip().lower() or "unknown"
        self.manifest_context["run_status"] = normalized_status
        resolved_completed_stage = completed_stage or self.last_completed_stage or ""
        if resolved_completed_stage:
            self.manifest_context["completed_stage"] = resolved_completed_stage
        if failure_reason:
            self.manifest_context["failure_reason"] = failure_reason
            resolved_failed_stage = failed_stage or self.current_stage_name or resolved_completed_stage
            if resolved_failed_stage:
                self.manifest_context["failed_stage"] = resolved_failed_stage
        else:
            self.manifest_context.pop("failure_reason", None)
            self.manifest_context.pop("failed_stage", None)

    def begin_stage(self, stage_name: str) -> None:
        """Track the active stage for failure reporting and the live run marker."""
        self.current_stage_name = stage_name
        self.active_perf_stage_start = perf_counter()
        self.manifest_context["current_stage"] = stage_name
        self.manifest_context["_active_stage_wall_start_iso"] = datetime.now(timezone.utc).isoformat()
        # A full run can spend hours inside one stage.  Keep the lightweight
        # on-disk capsule current so an operator can distinguish a live run at
        # ``training`` from a stale ``.RUNNING`` marker after an interruption.
        run_root = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
        if run_root:
            try:
                touch_run_lifecycle_running(Path(run_root), stage=stage_name)
            except OSError:
                # Lifecycle decoration must never block the scientific stage.
                pass
        obs_begin = self.manifest_context.get("pipeline_observability")
        if isinstance(obs_begin, PipelineObservabilitySession):
            obs_begin.emit_stage_start(stage_name, stop_after=str(self.manifest_context.get("stop_after", "")))

    def attach_runtime_timing_context(self) -> None:
        total_runtime = max(0.0, perf_counter() - self.pipeline_started_at)
        self.manifest_context["stage_timings_sec"] = {
            k: round(v, 3) for k, v in self.stage_timings_sec.items()
        }
        self.manifest_context["pipeline_runtime_sec"] = round(total_runtime, 3)
        if self.last_completed_stage and "completed_stage" not in self.manifest_context:
            self.manifest_context["completed_stage"] = self.last_completed_stage
        if self.stage_timings_sec:
            timings_df = pd.DataFrame(
                [
                    {"stage": stage, "duration_sec": round(duration, 3)}
                    for stage, duration in self.stage_timings_sec.items()
                ]
            )
            timings_df["run_id"] = self.run_id
            timings_df["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
            timings_csv = timings_df.to_csv(index=False)
            diag = self._diagnostics_dir_getter()
            t_paths = oh.mirror_csv_text_run_then_global(
                diagnostics_dir=Path(diag),
                run_filename=f"pipeline_stage_timings_{self.run_id}.csv",
                csv_text=timings_csv,
                global_latest_name="pipeline_stage_timings.latest.csv",
            )
            for p in t_paths:
                sp = str(p)
                if sp not in self.artifact_list:
                    self.artifact_list.append(sp)

    def finalize_with_manifest_timing(
        self,
        *,
        profile: dict[str, Any],
        samples_df: pd.DataFrame | None,
        pipeline_results: dict[str, Any],
        vendor_eval: pd.DataFrame | None,
    ) -> int:
        """Finalize run manifest and record manifest stage timing."""
        stage_started = perf_counter()
        self.attach_runtime_timing_context()
        result = resolve_main_override("finalize_run_manifest_stage", finalize_run_manifest_stage)(
            manifest_context=self.manifest_context,
            profile=profile,
            samples_df=samples_df,
            pipeline_results=pipeline_results,
            vendor_eval_df=vendor_eval,
            artifact_list=self.artifact_list,
        )
        if result != 0:
            run_status = str(self.manifest_context.get("run_status", "") or "").strip().lower()
            if run_status in {"failed", "interrupted"}:
                du.print_warning(
                    f"[PIPELINE] Run manifest finalized with terminal run_status={run_status}."
                )
            else:
                du.print_error("[INTEGRITY] Run manifest write failure.")
        self.record_stage_timing("manifest", stage_started, record_observability=False)
        self.attach_runtime_timing_context()
        try:
            run_root = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
            if run_root:
                finalize_run_lifecycle_terminal(
                    Path(run_root),
                    manifest_context=self.manifest_context,
                    manifest_stage_result_code=int(result),
                )
                merge_lifecycle_fields_into_run_summaries(
                    run_root=Path(run_root),
                    diagnostics_dir=Path(self._diagnostics_dir_getter()),
                    run_id=self.run_id,
                    manifest_context=self.manifest_context,
                )
        except Exception:
            pass
        return result

    def write_preflight(self, status: str, reason: str = "") -> None:
        """Write evidence-mode preflight report for auditability."""
        evidence_on = bool(
            getattr(
                app_config,
                "EVIDENCE_MODE_ENABLED",
                getattr(app_config, "PAPER_MODE_ENABLED", False),
            )
        )
        samples_cohort_audit = str(self.stop_after).strip().lower() == "samples"
        forced_terminal_failure = str(status).strip().lower() in {"failed", "interrupted"}
        if not evidence_on and not samples_cohort_audit and not forced_terminal_failure:
            return
        run_root = Path(str(getattr(app_config, "RUNTIME_RUN_ROOT", app_config.DEFAULT_OUTPUT_DIR)))
        diagnostics_dir = run_root / "diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        if self.preflight_path is None:
            self.preflight_path = diagnostics_dir / "preflight_report.json"
        if samples_cohort_audit:
            self.preflight_payload[cohort_vocabulary.KEY_SAMPLES_STAGE_COHORT_COUNTS] = {
                "stop_after": self.stop_after,
                "cohort_sql_scope_row_count": self.manifest_context.get("cohort_sql_scope_row_count"),
                "cohort_prepared_row_count": self.manifest_context.get("cohort_prepared_row_count"),
            }
        if self.manifest_context.get("cohort_distinct_sample_id") is not None:
            self.preflight_payload["cohort_sample_id_integrity"] = {
                "cohort_prepared_row_count": self.manifest_context.get("cohort_prepared_row_count"),
                "cohort_distinct_sample_id": self.manifest_context.get("cohort_distinct_sample_id"),
                "cohort_duplicate_surplus_rows": self.manifest_context.get("cohort_duplicate_surplus_rows"),
            }
        self.preflight_payload.update(
            {
                "run_id": self.run_id,
                "profile_id": self.manifest_context.get("profile_id")
                or (self.manifest_context.get("profile_params", {}) or {}).get("profile_id"),
                "status": status,
                "reason": reason,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "config_hash": self.manifest_context.get("config_hash", ""),
                "evidence_mode": self.manifest_context.get("evidence_mode", {}),
            }
        )
        preflight_text = json.dumps(self.preflight_payload, indent=2, sort_keys=True)
        self.preflight_path.write_text(preflight_text, encoding="utf-8")
        output_root_raw = str(getattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", "") or "").strip()
        if output_root_raw:
            compatibility_path = Path(output_root_raw) / "runs" / self.run_id / "diagnostics" / "preflight_report.json"
            if compatibility_path != self.preflight_path:
                try:
                    compatibility_path.parent.mkdir(parents=True, exist_ok=True)
                    compatibility_path.write_text(preflight_text, encoding="utf-8")
                except Exception:
                    pass
        if str(self.preflight_path) not in self.artifact_list:
            self.artifact_list.append(str(self.preflight_path))

    def fail_pipeline(self, reason: str, *, stage_name: str | None = None) -> None:
        """Route expected stage failures through the shared finalization path."""
        if stage_name:
            self.begin_stage(stage_name)
        self.mark_run_state(
            "failed",
            failure_reason=reason,
            failed_stage=stage_name or self.current_stage_name,
        )
        self.write_preflight(status="failed", reason=reason)
        raise PipelineStageFailure(reason)
