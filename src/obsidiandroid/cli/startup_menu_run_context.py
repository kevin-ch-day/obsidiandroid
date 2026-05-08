"""Run context helpers for the interactive startup menu (manifest pointers, summaries).

Extracted from ``obsidiandroid.cli.startup_menu`` to keep the menu module smaller.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config import app_config

from .menu import run_locator
from .ui import display as du

def read_latest_run_id() -> str | None:
    """Return latest run_id using manifest timestamps before legacy pointers."""
    return run_locator.read_latest_run_id()


def discover_latest_run_id_from_runs(output_root: Path) -> tuple[tuple[int, datetime, str] | None, str] | None:
    """Return newest run candidate discovered from run-scoped manifests."""
    del output_root
    run_id = run_locator.discover_latest_run_id_from_runs()
    if not run_id:
        return None
    return (run_locator.candidate_sort_key(run_id=run_id), run_id)


def candidate_sort_key(
    *,
    run_id: str,
    manifest_payload: dict[str, object] | None = None,
) -> tuple[int, datetime, str] | None:
    """Build comparable sort key for run candidates, preferring valid timestamps."""
    return run_locator.candidate_sort_key(run_id=run_id, manifest_payload=manifest_payload)


def parse_run_timestamp_from_manifest(manifest_payload: dict[str, object]) -> datetime | None:
    """Parse timestamp from manifest payload when available."""
    return run_locator.parse_run_timestamp_from_manifest(manifest_payload)


def parse_run_timestamp_from_id(run_id: str) -> datetime | None:
    """Parse timestamp embedded in canonical run IDs."""
    return run_locator.parse_run_timestamp_from_id(run_id)


def read_locked_paper_run_id() -> str | None:
    """Return locked evidence run ID pointer when available."""
    return run_locator.read_locked_paper_run_id()


def paper_exports_available(run_id: str | None) -> bool:
    """Return whether publication exports exist for a given run ID."""
    token = str(run_id or "").strip()
    if not token:
        return False
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    paper_dir = output_root / "runs" / token / "paper_exports"
    return paper_dir.exists() and paper_dir.is_dir()


def has_structural_bundle(run_id: str | None) -> bool:
    """Return whether structural bundle exists for a given run ID."""
    token = str(run_id or "").strip()
    if not token:
        return False
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    bundle_dir = output_root / "runs" / token / "bundles" / "permission_trends"
    return bundle_dir.exists() and bundle_dir.is_dir()


def latest_run_context_status() -> dict[str, object]:
    """Build lightweight run-context status for state-aware menus."""
    latest_run_id = read_latest_run_id()
    locked_paper_run_id = read_locked_paper_run_id()
    return {
        "latest_run_id": latest_run_id or "",
        "locked_paper_run_id": locked_paper_run_id or "",
        "has_latest_run": bool(latest_run_id),
        "has_structural_bundle": has_structural_bundle(latest_run_id),
        "has_paper_exports": paper_exports_available(latest_run_id),
        "has_locked_paper_run": bool(locked_paper_run_id),
    }


def latest_run_paper_mode_enabled() -> bool:
    """Return whether latest run manifest indicates evidence mode enabled."""
    run_id = read_latest_run_id()
    if not run_id:
        return False
    manifest, _ = resolve_manifest_for_run_id(run_id)
    paper_mode = {}
    if isinstance(manifest, dict):
        paper_mode = manifest.get("evidence_mode") or manifest.get("paper_mode", {})
    if isinstance(paper_mode, dict):
        return bool(paper_mode.get("resolved_value", False))
    return False


def latest_run_has_provenance() -> bool:
    """Return whether key run-scoped provenance files exist for latest run."""
    run_id = read_latest_run_id()
    if not run_id:
        return False
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    diagnostics = output_root / "runs" / run_id / "diagnostics"
    split_ledger = diagnostics / f"split_freeze_headline_{run_id}.csv"
    split_legacy = diagnostics / f"split_freeze_audit_{run_id}.csv"
    required = [
        split_ledger if split_ledger.exists() else split_legacy,
        diagnostics / f"run_paths_manifest_{run_id}.json",
        diagnostics / f"experiment_registry_{run_id}.json",
    ]
    return all(path.exists() for path in required)


def print_availability_block(*, rows: list[tuple[str, str]]) -> None:
    """Print compact availability summary for state-sensitive menus."""
    du.print_subheader("Current State")
    for label, value in rows:
        du.print_stat(label, value)
    print("")


def status_text(enabled: bool, *, ready: str = "Ready", pending: str = "Pending") -> str:
    """Return normalized yes/no style status text."""
    return ready if bool(enabled) else pending


def read_latest_run_manifest() -> dict:
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


def read_json_object(path: Path) -> dict:
    """Read JSON file as dict; return empty dict on failure."""
    return run_locator.read_json_object(path)


def resolve_manifest_for_run_id(run_id: str) -> tuple[dict, Path]:
    """Resolve canonical run-scoped manifest for a specific run ID."""
    return run_locator.resolve_manifest_for_run_id(run_id)


def resolve_latest_manifest_payload() -> tuple[dict, str | None, Path]:
    """Resolve latest manifest payload, following pointer manifest when needed."""
    return run_locator.resolve_latest_manifest_payload()


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


def print_startup_context() -> None:
    """Print lightweight session context before showing the main menu."""
    context = latest_run_context_status()
    latest_run_id = str(context.get("latest_run_id", "")).strip() or "None yet"
    publication_ready = bool(context.get("has_paper_exports", False))
    provenance_ready = latest_run_has_provenance()

    du.print_rule(" ObsidianDroid ")
    du.print_info(
        f"Latest run {latest_run_id} · "
        f"Diagnostics {status_text(provenance_ready, ready='ready', pending='missing')} · "
        f"Paper exports {status_text(publication_ready, ready='ready', pending='none')}"
    )
    print("")

