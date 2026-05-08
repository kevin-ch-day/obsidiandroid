"""Run overview, history table, and session/output details for the startup menu."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from config import app_config

from .startup_menu_run_context import (
    candidate_sort_key,
    format_run_status_display,
    format_stage_label,
    latest_run_has_provenance,
    paper_exports_available,
    read_json_object,
    read_latest_run_id,
    read_locked_paper_run_id,
    read_run_progress_summary,
    read_run_summary,
    read_top_model_snapshot,
    resolve_latest_manifest_payload,
    resolve_run_root_for_manifest,
)
from .ui import display as du


def show_latest_run_snapshot() -> int:
    """Print a concise snapshot of the latest run manifest."""
    du.print_section("Current Run Summary")
    manifest, resolved_run_id, manifest_path = resolve_latest_manifest_payload()
    if not manifest:
        du.print_warning("[MENU] Latest run manifest not found at output/diagnostics/run_manifest.latest.json")
        return 1

    run_id = str(resolved_run_id or manifest.get("run_id", "unknown"))
    run_root = resolve_run_root_for_manifest(
        manifest,
        run_id=run_id,
        manifest_path=manifest_path,
    )
    canonical_manifest_path = run_root / "run_manifest.json"
    run_summary = read_run_summary(run_root)
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
        run_status = format_run_status_display(str(run_summary.get("run_status", "")))
        completed_stage = format_stage_label(str(run_summary.get("completed_stage", "")))
        runtime_total = None
    else:
        run_status, completed_stage, runtime_total = read_run_progress_summary(run_root)

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
        fallback_model, fallback_macro = read_top_model_snapshot(run_root, run_id)
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


def show_recent_runs_overview(limit: int = 10, *, include_noncanonical: bool = False) -> int:
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
        manifest = read_json_object(manifest_path)
        if not manifest:
            continue
        model_summary = manifest.get("model_summary") if isinstance(manifest.get("model_summary"), dict) else {}
        profile = manifest.get("profile_params") if isinstance(manifest.get("profile_params"), dict) else {}
        run_id = str(manifest.get("run_id", run_dir.name)).strip()
        run_root = resolve_run_root_for_manifest(
            manifest,
            run_id=run_id,
            manifest_path=manifest_path,
        )
        run_summary = read_run_summary(run_root)
        runtime_sec = run_summary.get("pipeline_runtime_sec", manifest.get("pipeline_runtime_sec"))
        _run_status, _completed_stage, runtime_total = read_run_progress_summary(run_root)
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
            fallback_model, fallback_macro = read_top_model_snapshot(run_root, run_id)
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
                "__sort_key": candidate_sort_key(run_id=run_id, manifest_payload=manifest),
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


def show_session_and_output_details() -> int:
    """Print active session and output-routing details."""
    du.print_section("Session and Output Details")
    output_root = Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
    latest_run_id = read_latest_run_id() or "None yet"
    locked_run_id = read_locked_paper_run_id() or "(none)"
    manifest, resolved_run_id, manifest_path = resolve_latest_manifest_payload()
    run_root = resolve_run_root_for_manifest(
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
    du.print_stat("Publication Exports", "Yes" if paper_exports_available(resolved_run_id or latest_run_id) else "No")
    du.print_stat("Run Diagnostics Available", "Yes" if latest_run_has_provenance() else "No")
    if manifest:
        du.print_stat(
            "Resolved Manifest",
            str(canonical_manifest_path if canonical_manifest_path.exists() else manifest_path),
        )
    return 0
