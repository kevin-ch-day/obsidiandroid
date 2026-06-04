"""Run context helpers for the interactive startup menu (manifest pointers, summaries).

Extracted from ``obsidiandroid.cli.startup_menu`` to keep the menu module smaller.
"""

from __future__ import annotations
from datetime import datetime
from pathlib import Path

import pandas as pd


from .menu.operator_state import (
    build_operator_state,
    has_structural_bundle as _shared_has_structural_bundle,
    latest_run_has_diagnostics as _shared_latest_run_has_diagnostics,
    latest_run_has_provenance as _shared_latest_run_has_provenance,
    output_root as _shared_output_root,
)
from .menu.run_artifact_state import resolve_model_comparison_summary_csv
from .menu import run_locator
from .ui import display as du

def read_latest_run_id() -> str | None:
    """Return latest run_id using manifest timestamps before legacy pointers."""
    return run_locator.read_latest_run_id()


def candidate_sort_key(
    *,
    run_id: str,
    manifest_payload: dict[str, object] | None = None,
) -> tuple[int, datetime, str] | None:
    """Build comparable sort key for run candidates, preferring valid timestamps."""
    return run_locator.candidate_sort_key(run_id=run_id, manifest_payload=manifest_payload)


def read_locked_publication_run_id() -> str | None:
    """Return locked evidence run ID pointer when available."""
    return run_locator.read_locked_publication_run_id()


def has_structural_bundle(run_id: str | None) -> bool:
    """Return whether structural bundle exists for a given run ID."""
    return _shared_has_structural_bundle(run_id, base=_shared_output_root().resolve())


def latest_run_context_status() -> dict[str, object]:
    """Build lightweight run-context status for state-aware menus."""
    shared = build_operator_state()
    latest_run_id = str(shared.get("latest_run_id", "") or "")
    locked_publication_run_id = str(
        shared.get("locked_publication_run_id", "") or shared.get("locked_run_id", "") or ""
    )
    return {
        "latest_run_id": latest_run_id or "",
        "locked_publication_run_id": locked_publication_run_id or "",
        "has_latest_run": bool(latest_run_id),
        "has_structural_bundle": bool(shared.get("has_structural_bundle", False)),
        "has_publication_exports": bool(shared.get("has_publication_exports", False)),
        "has_locked_publication_run": bool(locked_publication_run_id),
        "latest_profile_id": str(shared.get("profile_id", "") or ""),
        "best_run_index_path": str(shared.get("best_run_index_path", "") or ""),
    }


def latest_run_publication_mode_enabled() -> bool:
    """Return whether latest run manifest indicates evidence mode enabled."""
    shared = build_operator_state()
    return bool(shared.get("publication_ready_mode", False))


def latest_run_has_provenance() -> bool:
    """Return whether key run-scoped provenance files exist for latest run."""
    shared = build_operator_state()
    token = str(shared.get("latest_run_id", "") or "").strip()
    return _shared_latest_run_has_provenance(token, base=_shared_output_root().resolve())


def latest_run_has_diagnostics() -> bool:
    """Return whether any run-scoped diagnostics artifacts exist for latest run."""
    shared = build_operator_state()
    token = str(shared.get("latest_run_id", "") or "").strip()
    return _shared_latest_run_has_diagnostics(token, base=_shared_output_root().resolve())


def print_availability_block(*, rows: list[tuple[str, str]]) -> None:
    """Print compact availability summary for state-sensitive menus."""
    du.print_subheader("Current State")
    for label, value in rows:
        du.print_stat(label, value)
    print("")


def status_text(enabled: bool, *, ready: str = "Ready", pending: str = "Pending") -> str:
    """Return normalized yes/no style status text."""
    return ready if bool(enabled) else pending


def read_json_object(path: Path) -> dict:
    """Read JSON file as dict; return empty dict on failure."""
    return run_locator.read_json_object(path)


def resolve_manifest_for_run_id(run_id: str) -> tuple[dict, Path]:
    """Resolve canonical run-scoped manifest for a specific run ID."""
    return run_locator.resolve_manifest_for_run_id(run_id)


def resolve_latest_manifest_payload(*, output_base: Path | None = None) -> tuple[dict, str | None, Path]:
    """Resolve latest manifest payload; see :func:`run_locator.resolve_latest_manifest_payload`."""
    return run_locator.resolve_latest_manifest_payload(output_base=output_base)


def resolve_run_root_for_manifest(
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


def read_run_summary(run_root: Path) -> dict:
    """Read canonical run summary for a run root when available."""
    return read_json_object(run_root / "run_summary.json")


def format_run_status_display(run_status: str | None) -> str:
    """Map run summary status tokens to operator-facing labels."""
    normalized = str(run_status or "").strip().lower()
    if normalized == "complete":
        return "Complete"
    if normalized == "failed":
        return "Failed"
    if normalized == "partial":
        return "Partial run available"
    return "Run metadata available"


def format_stage_label(stage_name: str | None) -> str:
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


def resolve_pipeline_timings_path(run_root: Path) -> Path | None:
    """Resolve stage timing export (run-scoped name preferred, then legacy .latest)."""
    manifest_payload = read_json_object(run_root / "run_manifest.json")
    run_id = str(manifest_payload.get("run_id", "") or run_root.name or "").strip()
    diag = run_root / "diagnostics"
    candidates = [
        diag / f"pipeline_stage_timings_{run_id}.csv",
        diag / "pipeline_stage_timings.latest.csv",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def read_run_progress_summary(run_root: Path) -> tuple[str, str, float | None]:
    """Read run progress summary from stage timing exports when available."""
    timings_path = resolve_pipeline_timings_path(run_root)
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
    completed_stage = format_stage_label(last_stage)
    duration_total: float | None = None
    if "duration_sec" in timings_df.columns:
        duration_values = pd.to_numeric(timings_df["duration_sec"], errors="coerce").dropna()
        if not duration_values.empty:
            duration_total = float(duration_values.sum())

    if str(last_stage).strip() == "manifest":
        return ("Complete", completed_stage, duration_total)
    return ("Partial run available", completed_stage, duration_total)


def read_top_model_snapshot(run_root: Path, run_id: str) -> tuple[str, str]:
    """Resolve top-model summary from run-scoped model comparison export."""
    summary_path = resolve_model_comparison_summary_csv(output_root=run_root.parent.parent, run_id=run_id)
    if summary_path is None:
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


def print_startup_context() -> None:
    """Print lightweight session context before showing the main menu."""
    context = latest_run_context_status()
    latest_run_id = str(context.get("latest_run_id", "")).strip() or "None yet"
    publication_ready = bool(context.get("has_publication_exports", False))
    diagnostics_ready = latest_run_has_diagnostics()
    provenance_ready = latest_run_has_provenance()
    diagnostics_status = "ready" if provenance_ready else "available" if diagnostics_ready else "missing"

    du.print_rule(" ObsidianDroid ")
    du.print_info(
        f"Latest run {latest_run_id} · "
        f"Diagnostics {diagnostics_status} · "
        f"Publication exports {status_text(publication_ready, ready='ready', pending='none')}"
    )
    print("")
