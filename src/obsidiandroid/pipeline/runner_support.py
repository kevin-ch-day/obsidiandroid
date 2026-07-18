"""Shared helpers for ``obsidiandroid.pipeline.runner`` (artifact list, stage errors, main sync).

Keeping these symbols out of ``runner.py`` reduces module size while preserving behavior:
``run_pipeline`` still owns diagnostics globals and ``_set_diagnostics_dir`` so tests can
monkeypatch ``pipeline.runner.DIAGNOSTICS_DIR`` unchanged.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Mapping

from obsidiandroid.cli.ui import display as du

from obsidiandroid.governance.integrity import enforce_run_scoped_artifact_paths


def sync_main_module_diagnostics(path: str) -> None:
    """Mirror diagnostics path onto ``main`` when loaded (tests patch ``main.DIAGNOSTICS_DIR``)."""
    main_mod = sys.modules.get("main")
    if main_mod is not None and hasattr(main_mod, "DIAGNOSTICS_DIR"):
        setattr(main_mod, "DIAGNOSTICS_DIR", path)


class ScopedArtifactList(list[str]):
    """Artifact list with immediate run-scope path enforcement on append/extend."""

    def __init__(
        self,
        *,
        strict_run_scoped: bool,
        run_root_getter: Callable[[], str],
        output_root_getter: Callable[[], str],
        allow_global_getter: Callable[[], bool],
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


class PipelineStageFailure(RuntimeError):
    """Expected pipeline-stage failure that should finalize cleanly."""


def restore_pipeline_runtime_state(
    *,
    stop_runtime_logging: Callable[[Any], None],
    runtime_log_context: Any,
    close_all_loggers: Callable[[], None],
    mutable_config_snapshot: Mapping[str, Any],
    config: Any,
    missing_sentinel: object,
    clear_run_bounds: Callable[[], None],
    set_diagnostics_dir: Callable[[str], None],
    original_diagnostics_dir: str,
) -> None:
    """Restore process-local state without allowing cleanup failures to leak.

    A pipeline can run repeatedly within the operator console.  Runtime logging,
    configuration overrides, run bounds, and the diagnostics path must therefore
    be restored independently: a failure in one cleanup action must not prevent
    the remaining actions from running.
    """

    def _warn(action: str, exc: Exception) -> None:
        du.print_warning(f"[CLEANUP] {action} failed: {exc}")

    try:
        stop_runtime_logging(runtime_log_context)
    except Exception as exc:
        _warn("runtime logging shutdown", exc)

    try:
        close_all_loggers()
    except Exception as exc:
        _warn("logger shutdown", exc)

    for key, original_value in mutable_config_snapshot.items():
        try:
            if original_value is missing_sentinel:
                if hasattr(config, key):
                    delattr(config, key)
            else:
                setattr(config, key, original_value)
        except Exception as exc:
            _warn(f"runtime configuration restore for {key}", exc)

    try:
        clear_run_bounds()
    except Exception as exc:
        _warn("pipeline run-bounds reset", exc)

    try:
        set_diagnostics_dir(original_diagnostics_dir)
    except Exception as exc:
        _warn("diagnostics-path restore", exc)


def _clean_failure_reason(error_text: str) -> str:
    reason = str(error_text).strip()
    for prefix in ("[INTEGRITY] ", "[PIPELINE] ", "[PROFILE] ", "[COHORT_LOCK] "):
        if reason.startswith(prefix):
            reason = reason[len(prefix) :].strip()
    return reason


def _stage_recovery_hint(stage_name: str | None, error_text: str) -> str:
    stage = str(stage_name or "").strip().lower()
    text = str(error_text).lower()
    if str(error_text).startswith("[INTEGRITY]"):
        return "Review the integrity-related diagnostics and the preflight report before rerunning."
    if stage == "samples":
        if "no samples found" in text:
            return "Review cohort gates, profile filters, and SQL scope diagnostics before rerunning."
        return "Review cohort readiness, SQL scope diagnostics, and sample preparation outputs."
    if stage == "av_pipeline":
        if "engine scoring" in text:
            return "Review engine lifecycle, AV scoring diagnostics, and score_av_engines logs before rerunning."
        if "binary matrix" in text or "score enrichment" in text:
            return "Review AV matrix build diagnostics and enriched matrix integrity before rerunning."
        return "Review AV pipeline diagnostics and engine metadata outputs."
    if stage == "vendor_metadata":
        return "Review vendor parser diagnostics, scorecards, and vendor raw artifacts."
    if stage == "feature_matrix":
        return "Review fused matrix diagnostics, feature-prune outputs, and modality contract artifacts."
    if stage == "alignment":
        return "Review aligned_labels, taxonomy authority diagnostics, and label-resolution outputs."
    if stage == "training":
        return "Review training diagnostics, split integrity, and model-specific logs."
    if stage == "ablation":
        return "Review ablation summaries and experiment-specific diagnostics to isolate the failing cell."
    return "Review diagnostics and rerun in debug mode if a traceback is needed."


def write_pipeline_failure_summary(
    *,
    diagnostics_dir: str,
    run_root: str,
    run_id: str,
    stage_name: str | None,
    error: Exception,
    preflight_path: str = "",
) -> list[str]:
    """Write compact machine/human-readable failure summary artifacts."""
    diag_dir = Path(str(diagnostics_dir).strip())
    if not str(diag_dir):
        return []
    diag_dir.mkdir(parents=True, exist_ok=True)
    error_text = str(error).strip() or repr(error)
    reason = _clean_failure_reason(error_text)
    payload = {
        "run_id": str(run_id).strip() or "unknown",
        "stage": str(stage_name or "unknown").strip() or "unknown",
        "error_type": error.__class__.__name__,
        "reason": reason,
        "integrity_stop": bool(error_text.startswith("[INTEGRITY]")),
        "recoverable_stage_failure": isinstance(error, PipelineStageFailure),
        "diagnostics_dir": str(diagnostics_dir),
        "run_root": str(run_root),
        "preflight_report": str(preflight_path or ""),
        "recommended_next_action": _stage_recovery_hint(stage_name, error_text),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    json_path = diag_dir / "failure_summary.json"
    md_path = diag_dir / "failure_summary.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Pipeline Failure Summary",
                "",
                f"- Run ID: `{payload['run_id']}`",
                f"- Stage: `{payload['stage']}`",
                f"- Error type: `{payload['error_type']}`",
                f"- Reason: {payload['reason']}",
                f"- Integrity stop: `{payload['integrity_stop']}`",
                f"- Controlled stage failure: `{payload['recoverable_stage_failure']}`",
                f"- Diagnostics dir: `{payload['diagnostics_dir']}`",
                f"- Preflight report: `{payload['preflight_report']}`" if payload["preflight_report"] else "- Preflight report: `(not written)`",
                f"- Run root: `{payload['run_root']}`",
                f"- Next: {payload['recommended_next_action']}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return [str(json_path), str(md_path)]


def register_pipeline_failure_summary(
    *,
    diagnostics_dir: str,
    run_root: str,
    run_id: str,
    stage_name: str | None,
    error: Exception,
    preflight_path: str,
    artifact_list: list[str],
    manifest_context: dict[str, Any],
) -> list[str]:
    """Write and register failure artifacts without masking the original error.

    Failure artifacts are valuable during both interrupted and failed runs, but
    an export problem must not replace the primary pipeline error or prevent its
    normal finalization path.
    """
    try:
        written_paths = write_pipeline_failure_summary(
            diagnostics_dir=diagnostics_dir,
            run_root=run_root,
            run_id=run_id,
            stage_name=stage_name,
            error=error,
            preflight_path=preflight_path,
        )
        for path in written_paths:
            if path not in artifact_list:
                artifact_list.append(path)
        manifest_context["failure_summary_path"] = next(
            (str(path) for path in written_paths if str(path).endswith("failure_summary.json")),
            "",
        )
        return written_paths
    except Exception as exc:
        du.print_warning(f"[FAILURE] Failure-summary export skipped: {exc}")
        return []


def emit_pipeline_failure_summary(
    *,
    stage_name: str | None,
    error: Exception,
    diagnostics_dir: str,
    run_root: str,
    preflight_path: str = "",
) -> None:
    """Print a compact operator-facing failure summary with next inspection points."""
    error_text = str(error).strip() or repr(error)
    error_type = error.__class__.__name__
    stage_display = str(stage_name or "unknown").strip() or "unknown"
    reason = _clean_failure_reason(error_text)
    title = "Integrity Stop" if error_text.startswith("[INTEGRITY]") else "Pipeline Failure"
    du.print_section(title)
    du.print_stat("Stage", stage_display)
    du.print_stat("Error type", error_type)
    du.print_stat("Reason", reason)
    if diagnostics_dir:
        du.print_stat("Diagnostics dir", du.format_console_path(diagnostics_dir))
    if preflight_path:
        du.print_stat("Preflight report", du.format_console_path(preflight_path))
    if run_root:
        du.print_stat("Run root", du.format_console_path(run_root))
    du.print_info(f"[NEXT] {_stage_recovery_hint(stage_display, error_text)}")
