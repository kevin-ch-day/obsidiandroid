"""Interactive startup menu for pipeline execution modes."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from typing import Callable, Dict, List

import pandas as pd

from config import app_config
from analysis.evaluation import engine_scoring_summary
from ml_classification.training import pipeline_core
from database import db_engine
from utils.ui import display as du
from utils.ui import menu as mu
from utils.menu import run_locator
from utils.menu.profile_preflight import resolve_and_validate_profile
from utils.menu.vendor_diagnostics import (
    run_single_vendor_parser_check,
    validate_parser_columns_from_latest_export,
)
from utils.menu import startup_menu_actions
from utils import output_hygiene as oh


@dataclass(frozen=True)
class _MenuCommand:
    """Descriptor for one operator-facing menu command."""

    label: str
    action: Callable[[], int | None]


def _run_full_pipeline(profile_id: str) -> int:
    """Run the complete pipeline with configured model set."""
    from main import run_pipeline

    return run_pipeline(profile_ref=profile_id)


def _run_single_model(model_key: str, profile_id: str) -> int:
    """Run the full pipeline while training only one selected model."""
    from main import run_pipeline

    return run_pipeline(selected_models=[model_key], profile_ref=profile_id)


def _run_vendor_only(profile_id: str) -> int:
    """Run pipeline through vendor metadata extraction and stop before ML."""
    from main import run_pipeline

    return run_pipeline(stop_after="vendor_metadata", profile_ref=profile_id)


def _run_engine_summary_only() -> int:
    """Generate engine scoring summary directly from DB and print top rows."""
    du.print_section("Engine Scoring Summary (DB Only)")
    summary_df = engine_scoring_summary.build_av_engine_scoring_summary_from_db()
    if summary_df is None or summary_df.empty:
        du.print_error("[MENU] Engine scoring summary returned no rows.")
        return 1

    du.print_success(f"[MENU] Engine summary rows: {len(summary_df)}")
    return 0


def _run_to_stage(profile_id: str) -> int:
    """Run pipeline and stop after a selected stage."""
    from main import run_pipeline

    stage_map: Dict[str, str] = {
        "Samples only": "samples",
        "AV pipeline only": "av_pipeline",
        "Vendor metadata only": "vendor_metadata",
        "Engine weights only": "engine_weights",
        "Feature matrix only": "feature_matrix",
        "Alignment only": "alignment",
        "Training only": "training",
        "Ablation only": "ablation",
        "Permission trends only": "permission_trends",
        "Label resolution only": "label_resolution",
    }
    choice = mu.display_menu(
        list(stage_map.keys()),
        title="Pipeline cutoff stage",
        exit_label="Back",
        breadcrumb="Main menu › Run analysis › Stage stop",
    )
    if choice == 0:
        return 0
    stage_names = list(stage_map.keys())
    stage_key = stage_map[stage_names[choice - 1]]
    return run_pipeline(stop_after=stage_key, profile_ref=profile_id)


def _build_model_menu() -> Dict[str, str]:
    """Return model menu mapping."""
    return {
        model.replace("_", " ").title(): model
        for model in pipeline_core.ALL_SUPPORTED_MODELS
    }


def _read_latest_run_id() -> str | None:
    """Return latest run_id using manifest timestamps before legacy pointers."""
    return run_locator.read_latest_run_id()


def _discover_latest_run_id_from_runs(output_root: Path) -> tuple[tuple[int, datetime, str] | None, str] | None:
    """Return newest run candidate discovered from run-scoped manifests."""
    del output_root
    run_id = run_locator.discover_latest_run_id_from_runs()
    if not run_id:
        return None
    return (run_locator.candidate_sort_key(run_id=run_id), run_id)


def _candidate_sort_key(
    *,
    run_id: str,
    manifest_payload: dict[str, object] | None = None,
) -> tuple[int, datetime, str] | None:
    """Build comparable sort key for run candidates, preferring valid timestamps."""
    return run_locator.candidate_sort_key(run_id=run_id, manifest_payload=manifest_payload)


def _parse_run_timestamp_from_manifest(manifest_payload: dict[str, object]) -> datetime | None:
    """Parse timestamp from manifest payload when available."""
    return run_locator.parse_run_timestamp_from_manifest(manifest_payload)


def _parse_run_timestamp_from_id(run_id: str) -> datetime | None:
    """Parse timestamp embedded in canonical run IDs."""
    return run_locator.parse_run_timestamp_from_id(run_id)


def _read_locked_paper_run_id() -> str | None:
    """Return locked evidence run ID pointer when available."""
    return run_locator.read_locked_paper_run_id()


def _paper_exports_available(run_id: str | None) -> bool:
    """Return whether publication exports exist for a given run ID."""
    token = str(run_id or "").strip()
    if not token:
        return False
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    paper_dir = output_root / "runs" / token / "paper_exports"
    return paper_dir.exists() and paper_dir.is_dir()


def _has_structural_bundle(run_id: str | None) -> bool:
    """Return whether structural bundle exists for a given run ID."""
    token = str(run_id or "").strip()
    if not token:
        return False
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    bundle_dir = output_root / "runs" / token / "bundles" / "permission_trends"
    return bundle_dir.exists() and bundle_dir.is_dir()


def _latest_run_context_status() -> dict[str, object]:
    """Build lightweight run-context status for state-aware menus."""
    latest_run_id = _read_latest_run_id()
    locked_paper_run_id = _read_locked_paper_run_id()
    return {
        "latest_run_id": latest_run_id or "",
        "locked_paper_run_id": locked_paper_run_id or "",
        "has_latest_run": bool(latest_run_id),
        "has_structural_bundle": _has_structural_bundle(latest_run_id),
        "has_paper_exports": _paper_exports_available(latest_run_id),
        "has_locked_paper_run": bool(locked_paper_run_id),
    }


def _latest_run_paper_mode_enabled() -> bool:
    """Return whether latest run manifest indicates evidence mode enabled."""
    run_id = _read_latest_run_id()
    if not run_id:
        return False
    manifest, _ = _resolve_manifest_for_run_id(run_id)
    paper_mode = {}
    if isinstance(manifest, dict):
        paper_mode = manifest.get("evidence_mode") or manifest.get("paper_mode", {})
    if isinstance(paper_mode, dict):
        return bool(paper_mode.get("resolved_value", False))
    return False


def _latest_run_has_provenance() -> bool:
    """Return whether key run-scoped provenance files exist for latest run."""
    run_id = _read_latest_run_id()
    if not run_id:
        return False
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    diagnostics = output_root / "runs" / run_id / "diagnostics"
    required = [
        diagnostics / f"split_freeze_audit_{run_id}.csv",
        diagnostics / f"run_paths_manifest_{run_id}.json",
        diagnostics / f"experiment_registry_{run_id}.json",
    ]
    return all(path.exists() for path in required)


def _print_availability_block(*, rows: list[tuple[str, str]]) -> None:
    """Print compact availability summary for state-sensitive menus."""
    du.print_subheader("Current State")
    for label, value in rows:
        du.print_stat(label, value)
    print("")


def _status_text(enabled: bool, *, ready: str = "Ready", pending: str = "Pending") -> str:
    """Return normalized yes/no style status text."""
    return ready if bool(enabled) else pending


def _read_latest_run_manifest() -> dict:
    """Return latest run manifest payload when available."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    manifest_path = output_root / "diagnostics" / "run_manifest.latest.json"
    if not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_json_object(path: Path) -> dict:
    """Read JSON file as dict; return empty dict on failure."""
    return run_locator.read_json_object(path)


def _resolve_manifest_for_run_id(run_id: str) -> tuple[dict, Path]:
    """Resolve canonical run-scoped manifest for a specific run ID."""
    return run_locator.resolve_manifest_for_run_id(run_id)


def _resolve_latest_manifest_payload() -> tuple[dict, str | None, Path]:
    """Resolve latest manifest payload, following pointer manifest when needed."""
    return run_locator.resolve_latest_manifest_payload()


def _resolve_run_root_for_manifest(
    manifest: dict,
    *,
    run_id: str | None,
    manifest_path: Path,
) -> Path:
    """Resolve run root for a manifest payload."""
    return run_locator.resolve_run_root_for_manifest(
        manifest,
        run_id=run_id,
        manifest_path=manifest_path,
    )


def _read_run_summary(run_root: Path) -> dict:
    """Read canonical run summary for a run root when available."""
    return _read_json_object(run_root / "run_summary.json")


def _format_run_status_display(run_status: str | None) -> str:
    """Map run summary status tokens to operator-facing labels."""
    normalized = str(run_status or "").strip().lower()
    if normalized == "complete":
        return "Complete"
    if normalized == "failed":
        return "Failed"
    if normalized == "partial":
        return "Partial run available"
    return "Run metadata available"


def _format_stage_label(stage_name: str | None) -> str:
    """Return user-facing label for a pipeline stage key."""
    stage_labels = {
        "samples": "Samples",
        "av_pipeline": "AV Pipeline",
        "vendor_metadata": "Vendor Metadata",
        "engine_weights": "Engine Weights",
        "feature_matrix": "Feature Matrix",
        "alignment": "Alignment",
        "training": "Training",
        "ablation": "Ablation",
        "permission_trends": "Permission Trends",
        "label_resolution": "Label Resolution",
        "manifest": "Manifest Finalization",
    }
    token = str(stage_name or "").strip()
    if not token:
        return "Unknown"
    return stage_labels.get(token, token.replace("_", " ").title())


def _resolve_pipeline_timings_path(run_root: Path) -> Path | None:
    """Resolve stage timing export (run-scoped name preferred, then legacy .latest)."""
    run_id = str(run_root.name or "").strip()
    diag = run_root / "diagnostics"
    candidates = [
        diag / f"pipeline_stage_timings_{run_id}.csv",
        diag / "pipeline_stage_timings.latest.csv",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _read_run_progress_summary(run_root: Path) -> tuple[str, str, float | None]:
    """Read run progress summary from stage timing exports when available."""
    timings_path = _resolve_pipeline_timings_path(run_root)
    if timings_path is None:
        return ("Run metadata available", "Manifest recorded", None)

    try:
        timings_df = pd.read_csv(timings_path)
    except Exception:
        return ("Run metadata available", "Manifest recorded", None)

    if timings_df.empty or "stage" not in timings_df.columns:
        return ("Run metadata available", "Manifest recorded", None)

    stage_series = timings_df["stage"].dropna().astype(str)
    if stage_series.empty:
        return ("Run metadata available", "Manifest recorded", None)

    last_stage = stage_series.iloc[-1]
    completed_stage = _format_stage_label(last_stage)
    duration_total: float | None = None
    if "duration_sec" in timings_df.columns:
        duration_values = pd.to_numeric(timings_df["duration_sec"], errors="coerce").dropna()
        if not duration_values.empty:
            duration_total = float(duration_values.sum())

    if str(last_stage).strip() == "manifest":
        return ("Complete", completed_stage, duration_total)
    return ("Partial run available", completed_stage, duration_total)


def _read_top_model_snapshot(run_root: Path, run_id: str) -> tuple[str, str]:
    """Resolve top-model summary from run-scoped model comparison export."""
    summary_path = run_root / "diagnostics" / f"model_comparison_summary_{run_id}.csv"
    if not summary_path.exists():
        return ("Not available yet", "Not available yet")

    try:
        summary_df = pd.read_csv(summary_path)
    except Exception:
        return ("Not available yet", "Not available yet")

    if summary_df.empty:
        return ("Not available yet", "Not available yet")

    top_row = summary_df.iloc[0]
    if "Top" in summary_df.columns:
        starred = summary_df[summary_df["Top"].astype(str).str.strip() == "*"]
        if not starred.empty:
            top_row = starred.iloc[0]
    elif "Rank" in summary_df.columns:
        ranked = summary_df.sort_values(by="Rank", ascending=True)
        if not ranked.empty:
            top_row = ranked.iloc[0]

    top_model = str(top_row.get("Model", "") or "").strip() or "Not available yet"
    raw_macro = top_row.get("Macro F1-Score")
    try:
        top_macro = f"{float(raw_macro):.4f}"
    except (TypeError, ValueError):
        top_macro = "Not available yet"
    return (top_model, top_macro)


def _print_startup_context() -> None:
    """Print lightweight session context before showing the main menu."""
    context = _latest_run_context_status()
    latest_run_id = str(context.get("latest_run_id", "")).strip() or "None yet"
    publication_ready = bool(context.get("has_paper_exports", False))
    provenance_ready = _latest_run_has_provenance()

    du.print_rule(" ObsidianDroid ")
    du.print_info(
        f"Latest run {latest_run_id} · "
        f"Diagnostics {_status_text(provenance_ready, ready='ready', pending='missing')} · "
        f"Paper exports {_status_text(publication_ready, ready='ready', pending='none')}"
    )
    print("")


def _show_latest_run_snapshot() -> int:
    """Print a concise snapshot of the latest run manifest."""
    du.print_section("Current Run Summary")
    manifest, resolved_run_id, manifest_path = _resolve_latest_manifest_payload()
    if not manifest:
        du.print_warning("[MENU] Latest run manifest not found at output/diagnostics/run_manifest.latest.json")
        return 1

    run_id = str(resolved_run_id or manifest.get("run_id", "unknown"))
    run_root = _resolve_run_root_for_manifest(
        manifest,
        run_id=run_id,
        manifest_path=manifest_path,
    )
    canonical_manifest_path = run_root / "run_manifest.json"
    run_summary = _read_run_summary(run_root)
    profile = str(
        run_summary.get("profile_id")
        or (manifest.get("profile_params") or {}).get("profile_id", "unknown")
    )
    cohort_size = run_summary.get("cohort_size", manifest.get("cohort_size", "n/a"))
    selected_vendor_count = run_summary.get(
        "selected_vendor_count",
        manifest.get("selected_vendor_count", "n/a"),
    )
    constrained = bool(
        run_summary.get(
            "vendor_constrained_run_flag",
            manifest.get("vendor_constrained_run_flag", False),
        )
    )
    if run_summary:
        run_status = _format_run_status_display(str(run_summary.get("run_status", "")))
        completed_stage = _format_stage_label(str(run_summary.get("completed_stage", "")))
        runtime_total = None
    else:
        run_status, completed_stage, runtime_total = _read_run_progress_summary(run_root)

    runtime_sec = run_summary.get("pipeline_runtime_sec", manifest.get("pipeline_runtime_sec"))
    if runtime_sec in (None, "", "n/a"):
        runtime_display = f"{runtime_total:.2f}" if runtime_total is not None else "Not available yet"
    else:
        runtime_display = runtime_sec

    top_model = str(
        run_summary.get("top_model")
        or (manifest.get("model_summary") or {}).get("top_model", "")
        or ""
    ).strip()
    raw_top_macro = run_summary.get(
        "top_macro_f1",
        (manifest.get("model_summary") or {}).get("top_macro_f1"),
    )
    try:
        top_macro = f"{float(raw_top_macro):.4f}"
    except (TypeError, ValueError):
        top_macro = ""

    if not top_model or not top_macro:
        fallback_model, fallback_macro = _read_top_model_snapshot(run_root, run_id)
        if not top_model:
            top_model = fallback_model
        if not top_macro:
            top_macro = fallback_macro

    du.print_stat("Run ID", run_id)
    du.print_stat("Profile", profile)
    du.print_stat("Run Status", run_status)
    du.print_stat("Completed Through Stage", completed_stage)
    du.print_stat("Cohort Size", cohort_size)
    du.print_stat("Selected Vendors", selected_vendor_count)
    du.print_stat("Vendor Constrained", constrained)
    du.print_stat("Pipeline Runtime (sec)", runtime_display)
    du.print_stat("Top Model", top_model)
    du.print_stat("Top Macro F1", top_macro)
    du.print_stat(
        "Run Manifest",
        str(canonical_manifest_path if canonical_manifest_path.exists() else manifest_path),
    )
    return 0


def _show_recent_runs_overview(limit: int = 10, *, include_noncanonical: bool = False) -> int:
    """Show a compact table of recent run manifests."""
    title = "Recent Run History"
    if include_noncanonical:
        title = "Full Run Folder History"
    du.print_section(title)
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    runs_root = output_root / "runs"
    if not runs_root.exists():
        du.print_warning(f"[MENU] Runs directory not found: {runs_root}")
        return 1

    rows: list[dict[str, object]] = []
    for run_dir in runs_root.iterdir():
        if not run_dir.is_dir():
            continue
        manifest_path = run_dir / "run_manifest.json"
        manifest = _read_json_object(manifest_path)
        if not manifest:
            continue
        model_summary = manifest.get("model_summary") if isinstance(manifest.get("model_summary"), dict) else {}
        profile = manifest.get("profile_params") if isinstance(manifest.get("profile_params"), dict) else {}
        run_id = str(manifest.get("run_id", run_dir.name)).strip()
        run_root = _resolve_run_root_for_manifest(
            manifest,
            run_id=run_id,
            manifest_path=manifest_path,
        )
        run_summary = _read_run_summary(run_root)
        runtime_sec = run_summary.get("pipeline_runtime_sec", manifest.get("pipeline_runtime_sec"))
        _run_status, _completed_stage, runtime_total = _read_run_progress_summary(run_root)
        if runtime_sec in (None, "", "n/a"):
            runtime_display: object = f"{runtime_total:.2f}" if runtime_total is not None else "Not available yet"
        else:
            runtime_display = runtime_sec

        top_model = str(run_summary.get("top_model") or model_summary.get("top_model", "") or "").strip()
        raw_top_macro = run_summary.get("top_macro_f1", model_summary.get("top_macro_f1"))
        try:
            top_macro: object = f"{float(raw_top_macro):.4f}"
        except (TypeError, ValueError):
            top_macro = ""

        if not top_model or not top_macro:
            fallback_model, fallback_macro = _read_top_model_snapshot(run_root, run_id)
            if not top_model:
                top_model = fallback_model
            if not top_macro:
                top_macro = fallback_macro

        rows.append(
            {
                "run_id": run_id,
                "profile": str(run_summary.get("profile_id") or profile.get("profile_id", "unknown")),
                "cohort_size": run_summary.get("cohort_size", manifest.get("cohort_size", "n/a")),
                "top_model": top_model or "Not available yet",
                "top_macro_f1": top_macro or "Not available yet",
                "runtime_sec": runtime_display,
                "timestamp_utc": str(
                    run_summary.get("timestamp_utc", manifest.get("timestamp_utc", ""))
                ),
                "__sort_key": _candidate_sort_key(run_id=run_id, manifest_payload=manifest),
            }
        )

    if not rows:
        du.print_warning("[MENU] No run-scoped manifests found under output/runs.")
        return 1

    valid_rows = [row for row in rows if row.get("__sort_key") is not None]
    hidden_noncanonical_count = 0
    if not include_noncanonical and valid_rows:
        hidden_noncanonical_count = len(rows) - len(valid_rows)
        rows = valid_rows

    rows.sort(
        key=lambda row: (
            row.get("__sort_key") is not None,
            row.get("__sort_key") or (0, datetime.min.replace(tzinfo=timezone.utc), ""),
            str(row.get("run_id", "")),
        ),
        reverse=True,
    )
    display_rows = []
    for row in rows[: max(1, int(limit))]:
        display_rows.append({key: value for key, value in row.items() if not str(key).startswith("__")})
    du.print_table(
        display_rows,
        title=f"Most recent runs (top {max(1, int(limit))})",
        show_index=False,
    )
    if hidden_noncanonical_count:
        du.print_note(
            f"[MENU] Hidden {hidden_noncanonical_count} non-canonical run folder(s); use Full Run Folder History to inspect them."
        )
    du.print_info("[MENU] Use Diagnostics > Run Health Check for Specific Run ID for deep validation.")
    return 0


def _show_session_and_output_details() -> int:
    """Print active session and output-routing details."""
    du.print_section("Session and Output Details")
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    latest_run_id = _read_latest_run_id() or "None yet"
    locked_run_id = _read_locked_paper_run_id() or "(none)"
    manifest, resolved_run_id, manifest_path = _resolve_latest_manifest_payload()
    run_root = _resolve_run_root_for_manifest(
        manifest,
        run_id=str(resolved_run_id or latest_run_id),
        manifest_path=manifest_path,
    )
    canonical_manifest_path = run_root / "run_manifest.json"

    du.print_stat("Environment", "Fedora Local Research")
    du.print_stat("Output Root", str(output_root))
    du.print_stat("Artifact Mode", "Run-scoped")
    du.print_stat("Latest Run", latest_run_id)
    du.print_stat("Locked Evidence Run", locked_run_id)
    du.print_stat("Publication Exports", "Yes" if _paper_exports_available(resolved_run_id or latest_run_id) else "No")
    du.print_stat("Run Diagnostics Available", "Yes" if _latest_run_has_provenance() else "No")
    if manifest:
        du.print_stat(
            "Resolved Manifest",
            str(canonical_manifest_path if canonical_manifest_path.exists() else manifest_path),
        )
    return 0


def _run_health_check(*, run_id: str | None = None) -> int:
    """Run lightweight checks for evidence readiness of latest or selected run."""
    title = "Quick Health Check"
    if run_id:
        title = f"Quick Health Check (run_id={run_id})"
    du.print_section(title)
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    diagnostics_dir = output_root / "diagnostics"
    latest_manifest_path = diagnostics_dir / "run_manifest.latest.json"

    rows: list[dict[str, str]] = []
    fail_count = 0
    warn_count = 0

    def _add_check(name: str, status: str, detail: str) -> None:
        """Append one health-check row and update aggregate status counters."""
        nonlocal fail_count, warn_count
        normalized = status.upper().strip()
        if normalized == "FAIL":
            fail_count += 1
        elif normalized == "WARN":
            warn_count += 1
        rows.append({"check": name, "status": normalized, "detail": detail})

    requested_run_id = (run_id or "").strip() or None
    latest_payload = _read_json_object(latest_manifest_path)
    resolved_run_id: str | None = None
    canonical_manifest: dict = {}
    canonical_manifest_path: Path | None = None

    if requested_run_id:
        canonical_manifest, canonical_manifest_path = _resolve_manifest_for_run_id(requested_run_id)
        if canonical_manifest:
            resolved_run_id = str(canonical_manifest.get("run_id", "")).strip() or requested_run_id
            _add_check("selected_run_manifest_exists", "PASS", str(canonical_manifest_path))
        else:
            _add_check(
                "selected_run_manifest_exists",
                "FAIL",
                f"Missing canonical manifest for run_id={requested_run_id}: {canonical_manifest_path}",
            )
    else:
        if not latest_payload:
            _add_check("latest_manifest_exists", "FAIL", f"Missing or unreadable {latest_manifest_path}")
        else:
            _add_check("latest_manifest_exists", "PASS", str(latest_manifest_path))
            canonical_manifest, resolved_run_id, canonical_manifest_path = _resolve_latest_manifest_payload()
            if canonical_manifest_path != latest_manifest_path and canonical_manifest:
                _add_check("canonical_manifest_exists", "PASS", str(canonical_manifest_path))

    if not canonical_manifest:
        du.print_table(rows, title="Run health checks", show_index=False)
        du.print_error("[MENU] Quick health check failed.")
        return 1

    effective_run_id = requested_run_id or resolved_run_id or str(canonical_manifest.get("run_id", "")).strip()
    if effective_run_id:
        _add_check("run_id_present", "PASS", effective_run_id)
    else:
        _add_check("run_id_present", "FAIL", "run_id missing in manifest payload.")

    canonical_run_id = str(canonical_manifest.get("run_id", "")).strip()
    if effective_run_id and canonical_run_id and effective_run_id != canonical_run_id:
        _add_check(
            "manifest_run_id_consistent",
            "FAIL",
            f"requested/latest run_id={effective_run_id} differs from canonical run_id={canonical_run_id}.",
        )
    else:
        _add_check("manifest_run_id_consistent", "PASS", canonical_run_id or effective_run_id or "n/a")

    run_root_dir = output_root / "runs" / (effective_run_id or "")
    if effective_run_id and run_root_dir.exists():
        _add_check("run_root_exists", "PASS", str(run_root_dir))
    elif effective_run_id:
        _add_check("run_root_exists", "WARN", f"Missing run-scoped directory: {run_root_dir}")

    run_summary = _read_run_summary(run_root_dir) if run_root_dir.exists() else {}
    if run_summary:
        _add_check("run_summary_exists", "PASS", str(run_root_dir / "run_summary.json"))
        run_status = str(run_summary.get("run_status", "")).strip().lower()
        if run_status == "failed":
            _add_check(
                "run_summary_status",
                "FAIL",
                str(run_summary.get("failure_reason", "run_summary.json marks run as failed")),
            )
        else:
            _add_check("run_summary_status", "PASS", run_status or "complete")
    elif run_root_dir.exists():
        _add_check("run_summary_exists", "WARN", f"Missing canonical run summary: {run_root_dir / 'run_summary.json'}")

    timestamp_utc = str(
        canonical_manifest.get("timestamp_utc", "") or latest_payload.get("created_at_utc", "")
    ).strip()
    if timestamp_utc:
        try:
            parsed_ts = datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - parsed_ts).total_seconds() / 3600.0
            if age_hours > 48:
                _add_check("latest_run_freshness", "WARN", f"Run age is {age_hours:.1f}h (>48h).")
            else:
                _add_check("latest_run_freshness", "PASS", f"Run age is {age_hours:.1f}h.")
        except ValueError:
            _add_check("latest_run_freshness", "WARN", f"Unparseable UTC timestamp: {timestamp_utc}")
    else:
        _add_check("latest_run_freshness", "WARN", "No timestamp found in latest manifest.")

    split_path = str((canonical_manifest.get("split") or {}).get("split_audit_path", "")).strip()
    if split_path:
        split_file = Path(split_path)
        _add_check(
            "split_audit_exists",
            "PASS" if split_file.exists() else "FAIL",
            str(split_file),
        )
    else:
        _add_check("split_audit_exists", "WARN", "No split_audit_path recorded in manifest.")

    model_config_path = str(canonical_manifest.get("model_config_snapshot_path", "")).strip()
    if model_config_path:
        model_config_file = Path(model_config_path)
    else:
        model_config_file = diagnostics_dir / "model_config_snapshot.latest.json"
    _add_check(
        "model_config_snapshot_exists",
        "PASS" if model_config_file.exists() else "FAIL",
        str(model_config_file),
    )

    vendor_gate_path = str(canonical_manifest.get("vendor_gate_debug_path", "")).strip()
    if vendor_gate_path:
        vendor_gate_file = Path(vendor_gate_path)
        _add_check(
            "vendor_gate_debug_exists",
            "PASS" if vendor_gate_file.exists() else "WARN",
            str(vendor_gate_file),
        )
    else:
        _add_check("vendor_gate_debug_exists", "WARN", "No vendor_gate_debug_path recorded in manifest.")

    parser_quality_path = diagnostics_dir / "parser_quality.latest.csv"
    parser_coverage_path = diagnostics_dir / "vendor_parser_coverage.latest.csv"
    _add_check(
        "parser_quality_snapshot_exists",
        "PASS" if parser_quality_path.exists() else "WARN",
        str(parser_quality_path),
    )
    _add_check(
        "parser_coverage_snapshot_exists",
        "PASS" if parser_coverage_path.exists() else "WARN",
        str(parser_coverage_path),
    )

    if effective_run_id:
        run_paths_manifest = diagnostics_dir / f"run_paths_manifest_{effective_run_id}.json"
        _add_check(
            "run_paths_manifest_exists",
            "PASS" if run_paths_manifest.exists() else "WARN",
            str(run_paths_manifest),
        )

    du.print_table(rows, title="Run health checks", show_index=False)
    report_run_id = effective_run_id or "unknown"
    report_payload = {
        "run_id": report_run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": {
            "pass": len(rows) - fail_count - warn_count,
            "warn": warn_count,
            "fail": fail_count,
        },
        "checks": rows,
    }
    report_latest = diagnostics_dir / "quick_health_check.latest.json"
    report_run = diagnostics_dir / f"quick_health_check_{report_run_id}.json"
    report_latest.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    report_run.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    du.print_info(f"[MENU] Health report: {report_run}")

    du.print_info(
        f"[MENU] Health summary: PASS={len(rows) - fail_count - warn_count}, "
        f"WARN={warn_count}, FAIL={fail_count}"
    )
    if fail_count:
        du.print_error("[MENU] Quick health check failed.")
        return 1
    if warn_count:
        du.print_warning("[MENU] Quick health check passed with warnings.")
        return 0
    du.print_success("[MENU] Quick health check passed.")
    return 0


def _run_quick_health_check() -> int:
    """Run quick health check for latest run."""
    return _run_health_check(run_id=None)


def _run_health_check_for_selected_run() -> int:
    """Prompt for a run ID and run health check for that run."""
    latest_run_id = _read_latest_run_id()
    selected = _prompt_run_id(default_run_id=latest_run_id)
    if not selected:
        du.print_warning("[MENU] Health check cancelled (no run_id provided).")
        return 1
    return _run_health_check(run_id=selected)


def _show_parser_diagnostics_snapshot() -> int:
    """Print compact parser diagnostics from latest CSV exports."""
    du.print_section("Parser Diagnostics Snapshot")
    diagnostics_dir = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output"))) / "diagnostics"
    coverage_path = diagnostics_dir / "vendor_parser_coverage.latest.csv"
    stress_path = diagnostics_dir / "vendor_parser_stress_test.latest.csv"
    strengths_path = diagnostics_dir / "vendor_parser_strengths_weaknesses.latest.csv"

    if not coverage_path.exists():
        du.print_warning("[MENU] Missing parser coverage snapshot. Run vendor metadata stage first.")
        return 1

    coverage_df = pd.read_csv(coverage_path)
    if coverage_df.empty:
        du.print_warning("[MENU] Parser coverage snapshot is empty.")
        return 1
    total = len(coverage_df)
    mapped = int(pd.to_numeric(coverage_df.get("parser_mapped", 0), errors="coerce").fillna(0).sum())
    du.print_stat("Observed Vendor Columns", total)
    du.print_stat("Mapped Parser Columns", mapped)
    du.print_stat("Unmapped Columns", max(0, total - mapped))

    if stress_path.exists():
        stress_df = pd.read_csv(stress_path)
        if not stress_df.empty:
            top_row = stress_df.iloc[0].to_dict()
            du.print_info(
                "[MENU] Best stress profile: "
                f"unknown_cut={top_row.get('unknown_cut')} "
                f"mapped_cut={top_row.get('mapped_cut')} "
                f"generic_cut={top_row.get('generic_cut')} "
                f"effective_share={top_row.get('effective_inclusion_share')}"
            )

    if strengths_path.exists():
        strengths_df = pd.read_csv(strengths_path)
        if not strengths_df.empty:
            if "inclusion_status" in strengths_df.columns:
                excluded_mask = strengths_df["inclusion_status"].astype(str).str.lower() == "exclude"
            else:
                excluded_mask = pd.Series([False] * len(strengths_df), index=strengths_df.index)
            excluded = strengths_df[excluded_mask]
            if not excluded.empty:
                du.print_table(
                    excluded[["vendor", "weakness_tags"]].head(10),
                    title="Top excluded vendors (weakness tags)",
                    show_index=False,
                )
    return 0


def _prompt_run_id(default_run_id: str | None = None) -> str | None:
    """Prompt user for run_id with optional default."""
    hint = default_run_id or ""
    prompt = f"Enter run_id [{hint}]: " if hint else "Enter run_id: "
    try:
        entered = input(prompt).strip()
    except KeyboardInterrupt:
        du.print_warning("[MENU] Run ID prompt interrupted.")
        return None
    if entered:
        return entered
    return default_run_id


def _run_backfill_results_warehouse() -> int:
    """Backfill warehouse tables from existing permission bundle artifacts."""
    du.print_section("Backfill Results Warehouse from Existing Artifacts")
    latest_run_id = _read_latest_run_id()
    run_id = _prompt_run_id(default_run_id=latest_run_id)
    if not run_id:
        du.print_warning("[MENU] Backfill cancelled (no run_id provided).")
        return 1

    script_path = Path("scripts/backfill_permission_trends_warehouse.py")
    if not script_path.exists():
        du.print_error(f"[MENU] Missing script: {script_path}")
        return 1

    cmd = [sys.executable, str(script_path), "--run-id", run_id]
    du.print_info(f"[MENU] Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        du.print_error(f"[MENU] Backfill failed with exit code {proc.returncode}.")
        return int(proc.returncode)

    du.print_success(f"[MENU] Warehouse backfill completed for run_id={run_id}.")
    return 0


def _run_results_warehouse_status() -> int:
    """Show whether key warehouse tables are populated for a selected run."""
    du.print_section("Results Warehouse Status")
    latest_run_id = _read_latest_run_id()
    run_id = _prompt_run_id(default_run_id=latest_run_id)
    if not run_id:
        du.print_warning("[MENU] Status check cancelled (no run_id provided).")
        return 1

    table_names = [
        "analysis_snapshot",
        "analysis_snapshot_sample",
        "permission_coverage_report",
        "dangerous_distribution_by_type",
        "type_permission_prevalence",
        "family_permission_profile",
        "group_permission_entropy",
        "family_jsd_matrix",
        "banker_permission_enrichment",
        "permission_discriminability_rank",
        "consensus_distribution",
        "per_family_performance_spread",
        "banker_permission_family_heterogeneity",
        "family_permission_cohesion",
        "banker_permission_trends_over_time",
    ]
    rows: list[dict[str, object]] = []
    total_rows = 0
    for table in table_names:
        query = f"SELECT COUNT(*) AS row_count FROM {table} WHERE run_id = %s"
        try:
            result = db_engine.execute_query(
                query,
                params=(run_id,),
                fetch=True,
                as_dataframe=True,
            )
            row_count = int(result.iloc[0]["row_count"]) if not result.empty else 0
        except Exception as exc:
            rows.append({"table_name": table, "row_count": "ERROR", "status": str(exc)})
            continue

        total_rows += row_count
        status = "OK" if row_count > 0 else "MISSING"
        rows.append({"table_name": table, "row_count": row_count, "status": status})

    du.print_table(
        rows,
        title=f"Warehouse table coverage for run_id={run_id}",
        show_index=False,
    )
    if total_rows == 0:
        du.print_warning(
            "[MENU] No rows found for this run_id. Use 'Backfill Results Warehouse from Existing Artifacts'."
        )
        return 1

    du.print_success(f"[MENU] Warehouse rows detected for run_id={run_id}: total={total_rows}")
    return 0


def _run_output_cleanup() -> int:
    """Run output cleanup in dry-run or apply mode."""
    return startup_menu_actions.run_output_cleanup()


def _run_paper_structural_diagnostics() -> int:
    """Generate consolidated structural diagnostics from latest artifacts."""
    du.print_section("Generate Structural Diagnostics")
    script_path = Path("scripts/research/generate_structural_diagnostics.py")
    if not script_path.exists():
        du.print_error(f"[MENU] Missing script: {script_path}")
        return 1
    cmd = [sys.executable, str(script_path)]
    env = os.environ.copy()
    evidence_mode = bool(
        getattr(app_config, "EVIDENCE_MODE_ENABLED", getattr(app_config, "PAPER_MODE_ENABLED", True))
    )
    env["SCYTALEDROID_EVIDENCE_MODE"] = "1" if evidence_mode else "0"
    env["SCYTALEDROID_FIGURE_MODE"] = str(getattr(app_config, "FIGURE_MODE", "publication"))
    env["SCYTALEDROID_ANALYSIS_SCOPE"] = str(getattr(app_config, "ANALYSIS_SCOPE", "all"))
    latest_run_id = _read_latest_run_id() or ""
    if latest_run_id:
        env["SCYTALEDROID_RUN_ID"] = latest_run_id
    env["SCYTALEDROID_OUTPUT_ROOT"] = str(Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output"))).resolve())
    du.print_info(f"[MENU] Running: {' '.join(cmd)}")
    du.print_info(
        "[MENU] Structural export context: "
        f"evidence_mode={env['SCYTALEDROID_EVIDENCE_MODE']} "
        f"figure_mode={env['SCYTALEDROID_FIGURE_MODE']} "
        f"analysis_scope={env['SCYTALEDROID_ANALYSIS_SCOPE']}"
    )
    proc = subprocess.run(cmd, check=False, env=env, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip())
    if proc.returncode != 0:
        du.print_error(f"[MENU] Diagnostics script failed with exit code {proc.returncode}.")
        return int(proc.returncode)
    output_path = ""
    for line in (proc.stdout or "").splitlines():
        if line.strip().lower().startswith("wrote:"):
            output_path = line.split(":", 1)[1].strip()
            break
    setattr(app_config, "RUNTIME_LAST_STRUCTURAL_OUTPUT", output_path)
    if output_path:
        du.print_success(f"[MENU] Structural diagnostics exported to {output_path}")
    else:
        du.print_success("[MENU] Structural diagnostics exported.")
    return 0


def _run_claim_artifact_map_scaffold() -> int:
    """Generate claim_artifact_map.csv from run path manifests."""
    du.print_section("Generate Claim Artifact Map Scaffold")
    script_path = Path("scripts/research/generate_claim_artifact_map.py")
    if not script_path.exists():
        du.print_error(f"[MENU] Missing script: {script_path}")
        return 1
    latest = _read_latest_run_id() or ""
    try:
        run_ids = input(f"Enter run IDs (comma-separated) [{latest}]: ").strip()
    except KeyboardInterrupt:
        du.print_warning("[MENU] Input interrupted.")
        return 1
    run_ids = run_ids or latest
    if not run_ids:
        du.print_warning("[MENU] No run IDs provided.")
        return 1
    cmd = [sys.executable, str(script_path), "--run-ids", run_ids]
    du.print_info(f"[MENU] Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        du.print_error(f"[MENU] claim_artifact_map generation failed with exit code {proc.returncode}.")
        return int(proc.returncode)
    return 0


def _run_paper2_freeze_checker() -> int:
    """Run strict reproducibility checks for supplied evidence run IDs."""
    du.print_section("Run Evidence Bundle Checker")
    script_path = Path("scripts/research/check_evidence_bundle.py")
    if not script_path.exists():
        du.print_error(f"[MENU] Missing script: {script_path}")
        return 1
    latest = _read_latest_run_id() or ""
    try:
        run_ids = input(f"Enter run IDs (comma-separated) [{latest}]: ").strip()
    except KeyboardInterrupt:
        du.print_warning("[MENU] Input interrupted.")
        return 1
    run_ids = run_ids or latest
    if not run_ids:
        du.print_warning("[MENU] No run IDs provided.")
        return 1
    cmd = [sys.executable, str(script_path), "--run-ids", run_ids]
    du.print_info(f"[MENU] Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        du.print_warning(
            "[MENU] Evidence bundle checker reported issues; inspect output/diagnostics/evidence_bundle_check.latest.json"
        )
        return int(proc.returncode)
    du.print_success("[MENU] Evidence bundle checker passed for supplied run IDs.")
    return 0


def _run_retrain_from_cached_alignment() -> int:
    """Retrain models quickly from cached aligned feature/label artifacts."""
    du.print_section("Retrain Models from Cached Alignment")
    script_path = Path("scripts/retrain_models_from_cached_alignment.py")
    if not script_path.exists():
        du.print_error(f"[MENU] Missing script: {script_path}")
        return 1
    cmd = [sys.executable, str(script_path)]
    du.print_info(f"[MENU] Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        du.print_error(f"[MENU] Cached retrain failed with exit code {proc.returncode}.")
        return int(proc.returncode)
    return 0


def _show_within_cross_type_error_snapshot() -> int:
    """Show latest within-type vs cross-type error summary when available."""
    return startup_menu_actions.show_within_cross_type_error_snapshot()


def _show_model_comparison_snapshot() -> int:
    """Show latest model-comparison snapshot from diagnostics when available."""
    return startup_menu_actions.show_model_comparison_snapshot()


def _handle_confusion_matrix_export() -> int:
    """Handle confusion-matrix export with run context and clear guidance."""
    return startup_menu_actions.handle_confusion_matrix_export()


def _show_disk_usage_summary() -> int:
    """Show compact disk-usage summary for output workspace directories."""
    return startup_menu_actions.show_disk_usage_summary()


def _show_contract_snapshot_viewer() -> int:
    """Show latest experiment contract highlights for quick reproducibility review."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    path = output_root / "diagnostics" / "experiment_contract_snapshot.latest.json"
    if not path.exists():
        du.print_warning(f"[MENU] Missing latest experiment contract: {path}")
        return 1
    payload = _read_json_object(path)
    if not payload:
        du.print_warning("[MENU] Latest experiment contract is unreadable.")
        return 1
    model_contract = payload.get("model_contract", {}) if isinstance(payload.get("model_contract"), dict) else {}
    split_contract = payload.get("split_contract", {}) if isinstance(payload.get("split_contract"), dict) else {}
    series = payload.get("experiment_series", {}) if isinstance(payload.get("experiment_series"), dict) else {}
    du.print_section("Contract Snapshot Viewer")
    du.print_stat("Run ID", payload.get("run_id", "n/a"))
    du.print_stat("Profile ID", payload.get("profile_id", "n/a"))
    du.print_stat("Split Hash", split_contract.get("split_hash", "n/a"))
    du.print_stat("Model Config Hash", model_contract.get("model_config_hash", "n/a"))
    du.print_stat(
        "No Retuning Across Perturbations",
        model_contract.get("no_model_retuning_across_perturbations", "n/a"),
    )
    du.print_stat("Series ID", series.get("series_id", "n/a"))
    return 0


def _show_experiment_series_comparison() -> int:
    """Show latest and previous series hashes to explain run-to-run drift quickly."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    path = output_root / "diagnostics" / "experiment_contract_snapshot.latest.json"
    payload = _read_json_object(path)
    if not payload:
        du.print_warning("[MENU] Latest experiment contract snapshot unavailable.")
        return 1
    series = payload.get("experiment_series", {}) if isinstance(payload.get("experiment_series"), dict) else {}
    rows = [
        {"field": "series_id", "value": series.get("series_id", "n/a")},
        {"field": "split_hash", "value": (series.get("series_key") or {}).get("split_hash", "n/a")},
        {"field": "profile_id", "value": (series.get("series_key") or {}).get("profile_id", "n/a")},
        {"field": "previous_run_id", "value": series.get("previous_run_id_in_series", "n/a")},
        {
            "field": "previous_model_config_hash",
            "value": series.get("previous_model_config_hash_in_series", "n/a"),
        },
        {
            "field": "model_config_hash_stable_with_series",
            "value": series.get("model_config_hash_stable_with_series", "n/a"),
        },
    ]
    du.print_table(rows, title="Experiment Series Comparison", show_index=False)
    return 0


def _run_paper2_series_aggregator() -> int:
    """Aggregate strict reproducibility runs into a macro-F1 comparison table."""
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    runs_root = output_root / "runs"
    if not runs_root.exists():
        du.print_warning("[MENU] No runs directory found.")
        return 1

    rows: list[dict[str, object]] = []
    for run_dir in sorted([p for p in runs_root.iterdir() if p.is_dir()]):
        pack_dir = run_dir / "paper2_pack"
        readiness_path = pack_dir / "evidence_readiness.json"
        manifest_path = pack_dir / "manifest.json"
        metrics_path = pack_dir / "model_metrics.json"
        if not readiness_path.exists() or not manifest_path.exists() or not metrics_path.exists():
            continue
        readiness = _read_json_object(readiness_path)
        if not readiness or str(readiness.get("status", "")).lower() != "ready":
            continue
        manifest = _read_json_object(manifest_path)
        metrics = _read_json_object(metrics_path)
        if not manifest or not metrics:
            continue
        model_summary = metrics.get("model_summary", {}) if isinstance(metrics, dict) else {}
        macro_f1 = model_summary.get("top_macro_f1") if isinstance(model_summary, dict) else None
        rows.append(
            {
                "run_id": str(manifest.get("run_id", "")),
                "experiment_id": str(manifest.get("config_hash", ""))[:12],
                "dataset_hash": str(manifest.get("dataset_hash", "")),
                "engine_list_hash": str(manifest.get("engine_list_hash", "")),
                "macro_f1": float(macro_f1) if macro_f1 is not None else None,
                "effective_k": int(manifest.get("effective_top_k", 0) or 0),
                "requested_k": int(manifest.get("k_requested", 0) or 0),
                "model": str(model_summary.get("top_model", "")) if isinstance(model_summary, dict) else "",
                "window_start_utc": str((((manifest.get("profile_params") or {}).get("cohort_gates") or {}).get("time_window_start_utc", ""))),
                "window_end_utc": str((((manifest.get("profile_params") or {}).get("cohort_gates") or {}).get("time_window_end_utc", ""))),
            }
        )

    if not rows:
        du.print_warning("[MENU] No strict reproducibility runs found for aggregation.")
        return 1

    baseline = rows[0]
    mismatch_fields = [
        "dataset_hash",
        "engine_list_hash",
        "requested_k",
        "effective_k",
        "model",
        "window_start_utc",
        "window_end_utc",
    ]
    mismatched = []
    for row in rows[1:]:
        for field in mismatch_fields:
            if str(row.get(field, "")) != str(baseline.get(field, "")):
                mismatched.append((str(row.get("run_id", "")), field))
                break
    if mismatched:
        du.print_error("[MENU] Aggregation rejected: evidence runs have mismatched experiment contracts.")
        mismatch_preview = [{"run_id": rid, "field": fld} for rid, fld in mismatched[:10]]
        du.print_table(mismatch_preview, title="Contract mismatch preview", show_index=False)
        return 1

    df = pd.DataFrame(rows).sort_values(["macro_f1", "run_id"], ascending=[False, True])
    out_path = output_root / "diagnostics" / "macro_f1_comparison.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    du.print_success(f"[MENU] Strict reproducibility series comparison exported: {out_path}")
    du.print_table(df, title="Strict Reproducibility Macro-F1 Comparison", show_index=False)
    return 0


def _print_structural_analysis_banner() -> None:
    """Print current structural-analysis mode and pruning contract."""
    paper_mode = bool(
        getattr(app_config, "EVIDENCE_MODE_ENABLED", getattr(app_config, "PAPER_MODE_ENABLED", True))
    )
    figure_mode = str(getattr(app_config, "FIGURE_MODE", "analysis"))
    analysis_scope = str(getattr(app_config, "ANALYSIS_SCOPE", "all"))
    max_perms = int(getattr(app_config, "MAX_PERMISSIONS_HEATMAP", 30))
    selection_method = str(getattr(app_config, "PERMISSION_SELECTION_METHOD", "discriminability"))
    min_family_support = int(getattr(app_config, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 50))
    min_family_support_model = int(getattr(app_config, "MIN_FAMILY_SUPPORT", 3))
    exclude_unknown = bool(getattr(app_config, "EXCLUDE_UNKNOWN_TYPE_IN_VISUALS", True))
    latest_run_id = _read_latest_run_id() or "No run selected"
    layer_map = {
        "type": "Type-Level",
        "family": "Family-Level",
        "banker": "Banker-Specific",
        "all": "Mixed (Type + Family + Banker)",
    }
    structural_layer = layer_map.get(analysis_scope, analysis_scope)

    snapshot_path: Path | None = None
    rid_disp = str(latest_run_id).strip()
    if rid_disp and rid_disp != "No run selected":
        stable_root = oh.resolve_stable_output_root_for_mirrors()
        snapshot_path = oh.resolve_analysis_snapshot_csv_path(
            stable_root / "runs" / rid_disp / "diagnostics",
            rid_disp,
        )
    type_count: str | int = "Not available"
    unknown_count: str | int = "Not computed yet"
    family_visual_count: str | int = "Not available"
    try:
        if snapshot_path is not None:
            snap_df = pd.read_csv(snapshot_path)
            if "type_slug" in snap_df.columns:
                types = (
                    snap_df["type_slug"]
                    .fillna("unknown")
                    .astype(str)
                    .str.strip()
                    .str.lower()
                )
                unknown_count = int((types == "unknown").sum())
                included_types = sorted(set(types.tolist()))
                if exclude_unknown:
                    included_types = [t for t in included_types if t != "unknown"]
                type_count = len(included_types)
            if "family_canonical" in snap_df.columns:
                fam_counts = (
                    snap_df["family_canonical"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .value_counts()
                )
                family_visual_count = int((fam_counts >= min_family_support).sum())
    except Exception:
        pass

    short_run_id = latest_run_id
    du.print_section("Structural Analysis Context")
    print("")
    print("Run")
    du.print_stat("  Active Run ID", short_run_id)
    du.print_stat("  Evidence Export Mode", "ON" if paper_mode else "OFF")
    du.print_stat("  Structural View Mode", "Publication" if str(figure_mode).lower() == "paper" else "Analysis")
    print("")
    print("Scope")
    du.print_stat("  Structural Layer", structural_layer)
    du.print_stat("  Analysis Scope", str(analysis_scope).title())
    du.print_stat("  Types Included", type_count)
    du.print_stat("  Exclude Unknown Type", "Yes" if exclude_unknown else "No")
    print("")
    print("Thresholds")
    du.print_stat("  Min Family Support", f"Visual >= {min_family_support} | Model >= {min_family_support_model}")
    du.print_stat("  Max Permissions", max_perms)
    du.print_stat("  Permission Selection", str(selection_method).title())
    print("")
    print("Cohort Snapshot")
    du.print_stat("  Unknown Samples", unknown_count)
    du.print_stat("  Families >= Visual", family_visual_count)


def _print_structural_result_card(*, action: str, status: str, output_path: str = "") -> None:
    """Print a compact action result card."""
    print("-" * 32 + " RESULT " + "-" * 31)
    du.print_stat("Action", action)
    if output_path:
        normalized = output_path.replace("\\", "/")
        du.print_stat("Output", normalized)
    du.print_stat("Status", status.upper())
    print("-" * 72)


def _warn_if_no_latest_run_context(*, area: str) -> None:
    """Warn users when entering run-dependent areas without a latest run."""
    if _read_latest_run_id():
        return
    du.print_warning(
        f"[MENU] {area}: no run selected yet. Some actions may be unavailable until a pipeline run completes."
    )


def _prompt_structural_analysis_action(options: List[str]) -> str:
    """Prompt for structural-analysis action with context refresh control."""
    du.print_subheader("Structural Analysis and Publication Figures")
    for idx, opt in enumerate(options, 1):
        print(f"  [{idx}] {opt}")
    print("  [I] View Context Card")
    print("  [0] Back\n")
    print("Controls: [I] Context  [0] Back")
    while True:
        try:
            raw = input(f"Enter your selection [0-{len(options)} or I]: ").strip()
        except KeyboardInterrupt:
            return "0"
        if not raw:
            du.print_warning("Invalid input. Please enter a selection.")
            continue
        token = raw.upper()
        if token == "I":
            return token
        if token.isdigit() and 0 <= int(token) <= len(options):
            return token
        du.print_warning("Invalid input. Enter a valid number or I.")


def _pipeline_run_mode_labels() -> list[str]:
    """Ordered labels for the primary pipeline launcher."""
    return [
        "Full pipeline",
        "Fast development",
        "Smoke test",
        "Single model only",
        "Stop after a stage",
        "Vendor extraction only",
        "Retrain from cached alignment",
    ]


def _launch_pipeline_actions_menu() -> int:
    """Display run actions and execute selected pipeline path."""
    while True:
        choice = mu.display_menu(
            _pipeline_run_mode_labels(),
            title="Pipeline run mode",
            exit_label="Back",
            breadcrumb="Main menu › Run analysis",
        )
        if choice == 0:
            return 0
        if choice == 1:
            profile_id = resolve_and_validate_profile(prefer_quick=True)
            if not profile_id:
                continue
            return _run_full_pipeline(profile_id)
        if choice == 2:
            return _run_full_pipeline("dev_fast")
        if choice == 3:
            return _run_full_pipeline("dev_smoke")
        if choice == 4:
            profile_id = resolve_and_validate_profile()
            if not profile_id:
                continue
            model_menu = _build_model_menu()
            model_choice = mu.display_menu(
                list(model_menu.keys()),
                title="Single model",
                exit_label="Back",
                breadcrumb="Main menu › Run analysis › Single model",
            )
            if model_choice == 0:
                continue
            model_names = list(model_menu.keys())
            model_key = model_menu[model_names[model_choice - 1]]
            return _run_single_model(model_key, profile_id)
        if choice == 5:
            profile_id = resolve_and_validate_profile()
            if not profile_id:
                continue
            return _run_to_stage(profile_id)
        if choice == 6:
            profile_id = resolve_and_validate_profile()
            if not profile_id:
                continue
            return _run_vendor_only(profile_id)
        if choice == 7:
            return _run_retrain_from_cached_alignment()
        du.print_warning("[MENU] Invalid choice received.")


def _launch_reuse_results_menu() -> None:
    """Display reuse actions for existing artifacts and warehouse tables."""
    while True:
        reuse = [
            "Backfill Results Warehouse from Existing Artifacts",
            "Check Results Warehouse Table Status",
        ]
        choice = mu.display_menu(
            reuse,
            title="Reuse existing results",
            exit_label="Back",
            breadcrumb="Main menu › Tools › Reuse",
        )
        if choice == 0:
            return
        if choice == 1:
            _run_backfill_results_warehouse()
            continue
        if choice == 2:
            _run_results_warehouse_status()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_maintenance_menu() -> None:
    """Display maintenance/diagnostic tools."""
    while True:
        maintenance = [
            "Engine Scoring Summary",
            "Parser Coverage Review",
            "Single Vendor Parser Diagnostic",
            "Parser Snapshot",
            "Run Health Check",
            "Structural Diagnostics",
            "Smart Output Cleanup",
            "Claim Artifact Map",
            "Evidence Bundle Checker",
        ]
        choice = mu.display_menu(
            maintenance,
            title="Maintenance tools",
            exit_label="Back",
            breadcrumb="Main menu › Tools › Maintenance",
        )
        if choice == 0:
            return
        if choice == 1:
            _run_engine_summary_only()
            continue
        if choice == 2:
            validate_parser_columns_from_latest_export()
            continue
        if choice == 3:
            run_single_vendor_parser_check()
            continue
        if choice == 4:
            _show_parser_diagnostics_snapshot()
            continue
        if choice == 5:
            _run_health_check_for_selected_run()
            continue
        if choice == 6:
            _run_paper_structural_diagnostics()
            continue
        if choice == 7:
            _run_output_cleanup()
            continue
        if choice == 8:
            _run_claim_artifact_map_scaffold()
            continue
        if choice == 9:
            _run_paper2_freeze_checker()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_structural_analysis_menu() -> None:
    """Display structural analysis and publication-figure workflows."""
    _warn_if_no_latest_run_context(area="Structural Analysis")
    show_context = True
    while True:
        context = _latest_run_context_status()
        has_latest_run = bool(context.get("has_latest_run", False))
        has_struct_bundle = bool(context.get("has_structural_bundle", False))
        has_paper_exports = bool(context.get("has_paper_exports", False))

        unavailable_reasons: dict[int, str] = {}
        if not has_latest_run:
            unavailable_reasons = {
                1: "no latest run",
                2: "no latest run",
                3: "no latest run",
                4: "no latest run",
                5: "no latest run",
            }
        elif not has_struct_bundle:
            unavailable_reasons[1] = "missing structural bundle"
            unavailable_reasons[2] = "missing structural bundle"
            unavailable_reasons[3] = "missing structural bundle"
            unavailable_reasons[4] = "missing structural bundle"
            unavailable_reasons[5] = "missing structural bundle"

        base_options: List[str] = [
            "Type-Level Analysis -> type heatmap + summary report",
            "Family-Level Analysis -> family visuals + diagnostics",
            "Banker-Specific Analysis -> banker trend artifacts",
            "Export Publication Figures -> presentation-ready figure set",
            "Export Structural Report -> full artifact pack",
        ]
        options: List[str] = []
        for idx, label in enumerate(base_options, start=1):
            reason = unavailable_reasons.get(idx, "").strip()
            if reason:
                options.append(f"{label} (Unavailable: {reason})")
            else:
                options.append(label)
        if show_context:
            _print_structural_analysis_banner()
            _print_availability_block(
                rows=[
                    ("Structural Bundle", "Yes" if has_struct_bundle else "No"),
                    ("Publication Exports", "Yes" if has_paper_exports else "No"),
                    ("Locked Evidence Run", "Yes" if bool(context.get("has_locked_paper_run", False)) else "No"),
                ]
            )
            show_context = False
        choice = _prompt_structural_analysis_action(options)
        if choice == "0":
            return
        if choice == "I":
            _print_structural_analysis_banner()
            continue
        selected_idx = int(choice)
        blocked_reason = unavailable_reasons.get(selected_idx, "").strip()
        if blocked_reason:
            du.print_warning(f"[MENU] Action unavailable: {blocked_reason}.")
            continue
        if choice == "1":
            setattr(app_config, "ANALYSIS_SCOPE", "type")
            result = _run_paper_structural_diagnostics()
            _print_structural_result_card(
                action="Type-Level Structural Analysis",
                status="success" if result == 0 else "failed",
                output_path=str(getattr(app_config, "RUNTIME_LAST_STRUCTURAL_OUTPUT", "")),
            )
            continue
        if choice == "2":
            setattr(app_config, "ANALYSIS_SCOPE", "family")
            result = _run_paper_structural_diagnostics()
            _print_structural_result_card(
                action="Family-Level Structural Analysis",
                status="success" if result == 0 else "failed",
                output_path=str(getattr(app_config, "RUNTIME_LAST_STRUCTURAL_OUTPUT", "")),
            )
            continue
        if choice == "3":
            setattr(app_config, "ANALYSIS_SCOPE", "banker")
            result = _run_paper_structural_diagnostics()
            _print_structural_result_card(
                action="Banker-Specific Structural Analysis",
                status="success" if result == 0 else "failed",
                output_path=str(getattr(app_config, "RUNTIME_LAST_STRUCTURAL_OUTPUT", "")),
            )
            continue
        if choice == "4":
            setattr(app_config, "EVIDENCE_MODE_ENABLED", True)
            setattr(app_config, "EVIDENCE_MODE_LOCKED_VALUE", True)
            setattr(app_config, "PAPER_MODE_ENABLED", True)
            setattr(app_config, "PAPER_MODE_LOCKED_VALUE", True)
            setattr(app_config, "FIGURE_MODE", "paper")
            result = _run_paper_structural_diagnostics()
            _print_structural_result_card(
                action="Export Publication Figures",
                status="success" if result == 0 else "failed",
                output_path=str(getattr(app_config, "RUNTIME_LAST_STRUCTURAL_OUTPUT", "")),
            )
            continue
        if choice == "5":
            setattr(app_config, "ANALYSIS_SCOPE", "all")
            if bool(getattr(app_config, "EVIDENCE_MODE_ENABLED", getattr(app_config, "PAPER_MODE_ENABLED", True))):
                setattr(app_config, "FIGURE_MODE", "paper")
            else:
                setattr(app_config, "FIGURE_MODE", "analysis")
            result = _run_paper_structural_diagnostics()
            _print_structural_result_card(
                action="Export Structural Report",
                status="success" if result == 0 else "failed",
                output_path=str(getattr(app_config, "RUNTIME_LAST_STRUCTURAL_OUTPUT", "")),
            )
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_model_evaluation_menu() -> None:
    """Display model evaluation and validation workflows."""
    _warn_if_no_latest_run_context(area="Model Evaluation")
    while True:
        context = _latest_run_context_status()
        has_latest_run = bool(context.get("has_latest_run", False))
        unavailable_reasons: dict[int, str] = {}
        if not has_latest_run:
            unavailable_reasons = {
                2: "no latest run",
                3: "no latest run",
                4: "no latest run",
                5: "no latest run",
            }

        base_options: List[str] = [
            "Engine Scoring Summary",
            "Within vs Cross-Type Errors",
            "Model Comparison",
            "Export Confusion Matrix",
            "Generate Claim Artifact Map",
        ]
        model_rows: List[str] = []
        for idx, label in enumerate(base_options, start=1):
            reason = unavailable_reasons.get(idx, "").strip()
            model_rows.append(f"{label} (Unavailable)" if reason else label)
        _print_availability_block(
            rows=[
                ("Latest Run", str(context.get("latest_run_id", "")) or "No"),
                ("Run-Scoped Provenance", "Yes" if _latest_run_has_provenance() else "No"),
            ]
        )
        choice = mu.display_menu(
            model_rows,
            title="Model evaluation",
            exit_label="Back",
            breadcrumb="Main menu › Research › Models",
        )
        if choice == 0:
            return
        blocked_reason = unavailable_reasons.get(int(choice), "").strip()
        if blocked_reason:
            du.print_warning(f"[MENU] Action unavailable: {blocked_reason}.")
            continue
        if choice == 1:
            _run_engine_summary_only()
            continue
        if choice == 2:
            _show_within_cross_type_error_snapshot()
            continue
        if choice == 3:
            _show_model_comparison_snapshot()
            continue
        if choice == 4:
            _handle_confusion_matrix_export()
            continue
        if choice == 5:
            _run_claim_artifact_map_scaffold()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_reproducibility_menu() -> None:
    """Display reproducibility and evidence-bundle workflows."""
    while True:
        context = _latest_run_context_status()
        locked_run_id = str(context.get("locked_paper_run_id", "")).strip()
        du.print_info(f"[MENU] Locked evidence run: {locked_run_id if locked_run_id else '(none)'}")
        has_latest_run = bool(context.get("has_latest_run", False))
        has_locked_paper_run = bool(context.get("has_locked_paper_run", False))
        latest_has_paper_exports = bool(context.get("has_paper_exports", False))
        latest_is_paper = _latest_run_paper_mode_enabled()
        latest_has_provenance = _latest_run_has_provenance()

        unavailable_reasons: dict[int, str] = {}
        if not has_latest_run:
            unavailable_reasons[2] = "no latest run"
            unavailable_reasons[3] = "no latest run"
            unavailable_reasons[4] = "no latest run"
            unavailable_reasons[5] = "no latest run"
            unavailable_reasons[6] = "no latest run"
        else:
            if not latest_is_paper:
                unavailable_reasons[3] = "latest run is not evidence mode"
            elif not latest_has_provenance:
                unavailable_reasons[3] = "required provenance files missing"
            if not has_locked_paper_run:
                unavailable_reasons[6] = "locked evidence run not set"

        base_options: List[str] = [
            "Run Health Check for Specific Run ID",
            "Quick Health Check (Latest)",
            "Evidence Bundle Checker",
            "Experiment Series Comparison",
            "Contract Snapshot Viewer",
            "Strict Reproducibility Series Aggregator",
        ]
        repro_rows: List[str] = []
        for idx, label in enumerate(base_options, start=1):
            reason = unavailable_reasons.get(idx, "").strip()
            repro_rows.append(f"{label} (Unavailable)" if reason else label)

        _print_availability_block(
            rows=[
                ("Locked Evidence Run", locked_run_id if locked_run_id else "No"),
                ("Latest Run Uses Evidence Mode", "Yes" if latest_is_paper else "No"),
                ("Latest Run Publication Exports", "Yes" if latest_has_paper_exports else "No"),
                ("Latest Run Provenance", "Yes" if latest_has_provenance else "No"),
            ]
        )
        choice = mu.display_menu(
            repro_rows,
            title="Reproducibility checks",
            exit_label="Back",
            breadcrumb="Main menu › Validation › Reproducibility",
        )
        if choice == 0:
            return
        blocked_reason = unavailable_reasons.get(int(choice), "").strip()
        if blocked_reason:
            du.print_warning(f"[MENU] Action unavailable: {blocked_reason}.")
            continue
        if choice == 1:
            _run_health_check_for_selected_run()
            continue
        if choice == 2:
            _run_quick_health_check()
            continue
        if choice == 3:
            _run_paper2_freeze_checker()
            continue
        if choice == 4:
            _show_experiment_series_comparison()
            continue
        if choice == 5:
            _show_contract_snapshot_viewer()
            continue
        if choice == 6:
            _run_paper2_series_aggregator()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_data_parser_menu() -> None:
    """Display parser/data diagnostics workflows."""
    while True:
        from utils.menu import vendor_diagnostics

        vendor_diagnostics.print_parser_diagnostics_state()
        data_diag = [
            "Validate Parser Coverage",
            "Run Single Vendor Parser Diagnostic",
            "Show Parser Diagnostics Snapshot",
        ]
        choice = mu.display_menu(
            data_diag,
            title="Data diagnostics",
            exit_label="Back",
            breadcrumb="Main menu › Validation › Data diagnostics",
        )
        if choice == 0:
            return
        if choice == 1:
            validate_parser_columns_from_latest_export()
            continue
        if choice == 2:
            run_single_vendor_parser_check()
            continue
        if choice == 3:
            _show_parser_diagnostics_snapshot()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_output_management_menu() -> None:
    """Display output and artifact hygiene workflows."""
    while True:
        output_opts = [
            "Cleanup Output Artifacts (Smart prune)",
            "Show Disk Usage Summary",
        ]
        choice = mu.display_menu(
            output_opts,
            title="Output management",
            exit_label="Back",
            breadcrumb="Main menu › Tools › Output",
        )
        if choice == 0:
            return
        if choice == 1:
            _run_output_cleanup()
            continue
        if choice == 2:
            _show_disk_usage_summary()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_run_overview_menu() -> None:
    """Display run overview and snapshot workflows."""
    while True:
        run_status = [
            "Current Run Summary",
            "Recent Run History",
            "Session and Output Details",
            "Full Run Folder History (Advanced)",
        ]
        choice = mu.display_menu(
            run_status,
            title="Run status and history",
            exit_label="Back",
            breadcrumb="Main menu › Run status",
        )
        if choice == 0:
            return
        if choice == 1:
            _show_latest_run_snapshot()
            continue
        if choice == 2:
            _show_recent_runs_overview()
            continue
        if choice == 3:
            _show_session_and_output_details()
            continue
        if choice == 4:
            _show_recent_runs_overview(include_noncanonical=True)
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_research_reports_menu() -> None:
    """Display research, reporting, and evaluation workflows."""
    while True:
        research = [
            "Structural Analysis",
            "Model Evaluation",
        ]
        choice = mu.display_menu(
            research,
            title="Research reports",
            exit_label="Back",
            breadcrumb="Main menu › Research",
        )
        if choice == 0:
            return
        if choice == 1:
            _launch_structural_analysis_menu()
            continue
        if choice == 2:
            _launch_model_evaluation_menu()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_validation_diagnostics_menu() -> None:
    """Display validation, reproducibility, and parser diagnostics workflows."""
    while True:
        validation = [
            "Reproducibility Checks",
            "Data Diagnostics",
        ]
        choice = mu.display_menu(
            validation,
            title="Validation and diagnostics",
            exit_label="Back",
            breadcrumb="Main menu › Validation",
        )
        if choice == 0:
            return
        if choice == 1:
            _launch_reproducibility_menu()
            continue
        if choice == 2:
            _launch_data_parser_menu()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _launch_operations_menu() -> None:
    """Display operational maintenance and artifact-management workflows."""
    while True:
        operations = [
            "Maintenance Tools",
            "Output Management",
            "Reuse Existing Results",
        ]
        choice = mu.display_menu(
            operations,
            title="Tools and maintenance",
            exit_label="Back",
            breadcrumb="Main menu › Tools",
        )
        if choice == 0:
            return
        if choice == 1:
            _launch_maintenance_menu()
            continue
        if choice == 2:
            _launch_output_management_menu()
            continue
        if choice == 3:
            _launch_reuse_results_menu()
            continue
        du.print_warning("[MENU] Invalid choice received.")


def _print_operator_console_summary() -> None:
    """Print a compact operator summary block ahead of the main menu."""
    context = _latest_run_context_status()
    latest_run_id = str(context.get("latest_run_id", "")).strip() or "None yet"
    du.print_section("Workspace Status")
    _print_availability_block(
        rows=[
            ("Latest Run", latest_run_id),
            ("Run Diagnostics", _status_text(_latest_run_has_provenance(), ready="Available", pending="Missing")),
            ("Publication Exports", _status_text(bool(context.get("has_paper_exports", False)), ready="Available", pending="Not built")),
        ]
    )


def _build_main_menu_commands() -> list[_MenuCommand]:
    """Return the redesigned top-level operator menu."""
    return [
        _MenuCommand(label="Run Analysis", action=_launch_pipeline_actions_menu),
        _MenuCommand(label="Run Status and History", action=_launch_run_overview_menu),
        _MenuCommand(label="Research Reports", action=_launch_research_reports_menu),
        _MenuCommand(label="Validation and Diagnostics", action=_launch_validation_diagnostics_menu),
        _MenuCommand(label="Tools and Maintenance", action=_launch_operations_menu),
        _MenuCommand(label="Clear Screen", action=lambda: 0),
    ]


def launch_startup_menu() -> int:
    """Run interactive startup menu loop."""
    _print_startup_context()

    while True:
        commands = _build_main_menu_commands()
        choice = mu.display_menu(
            [c.label for c in commands],
            title="Main menu",
            exit_label="Exit",
            breadcrumb="ObsidianDroid · operator console",
        )

        if choice == 0:
            du.print_info("[MENU] Exit requested.")
            return 0

        selected = commands[choice - 1]
        if selected.label == "Clear Screen":
            du.clear_console()
            _print_startup_context()
            continue

        result = selected.action()
        if isinstance(result, int) and result != 0:
            return result
        continue


def main() -> int:
    """Module CLI entrypoint."""
    try:
        return launch_startup_menu()
    except KeyboardInterrupt:
        du.print_warning("[MENU] Interrupted by user (Ctrl+C). Exiting.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
