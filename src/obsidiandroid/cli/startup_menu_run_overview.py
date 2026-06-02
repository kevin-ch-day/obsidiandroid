"""Run overview, history table, and session/output details for the startup menu."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from obsidiandroid.common.cohort_methodology import taxonomy_label_drift_display
from obsidiandroid.common.cohort_presentation import cohort_methodology_summary
from obsidiandroid.common.output_paths import output_root as canonical_output_root
from obsidiandroid.governance.evidence_mode_resolver import coalesce_manifest_publication_mode

from .menu.operator_state import build_operator_state
from .startup_menu_run_context import (
    candidate_sort_key,
    format_run_status_display,
    format_stage_label,
    read_json_object,
    read_run_progress_summary,
    read_run_summary,
    read_top_model_snapshot,
    resolve_run_root_for_manifest,
)
from .ui import display as du


def _compact_kv_map(d: dict[str, Any], *, max_keys: int = 16) -> str:
    if not d:
        return "— (profile defaults)"
    keys = sorted(d.keys())
    parts: list[str] = []
    for key in keys[:max_keys]:
        parts.append(f"{key}={d[key]!r}")
    tail = " …" if len(keys) > max_keys else ""
    return "; ".join(parts) + tail


def print_profile_tuning_from_manifest(manifest: dict[str, Any]) -> None:
    """Print cohort gates, dataset filters, parser/runtime overrides, and feature flags from manifest."""
    du.print_subheader("Profile tuning (frozen manifest)")
    pp = manifest.get("profile_params") if isinstance(manifest.get("profile_params"), dict) else {}
    if not pp:
        du.print_note(
            "No profile_params in this manifest. Pointer-only stubs omit it; open "
            "`output/runs/<run_id>/run_manifest.json` for the full frozen profile."
        )
        print("")
        return

    ch = str(manifest.get("config_hash", "") or "").strip()
    if ch:
        du.print_stat("Profile config hash", ch[:16] + ("…" if len(ch) > 16 else ""))

    manifest_publication_mode = coalesce_manifest_publication_mode(manifest)
    profile_evidence_mode = bool(pp.get("evidence_mode"))
    du.print_stat("Evidence mode (manifest)", "Yes" if manifest_publication_mode else "No")
    du.print_stat("Publication-ready mode (manifest)", "Yes" if manifest_publication_mode else "No")
    pmd = (
        manifest.get("evidence_mode")
        if isinstance(manifest.get("evidence_mode"), dict)
        else (manifest.get("paper_mode") if isinstance(manifest.get("paper_mode"), dict) else {})
    )
    psrc = str(pmd.get("source") or "").strip()
    if psrc:
        du.print_stat("Publication-ready mode source", psrc)
    if profile_evidence_mode != bool(manifest_publication_mode):
        du.print_stat("Evidence mode (profile)", "Yes" if profile_evidence_mode else "No")
    kreq = manifest.get("k_requested")
    effk = manifest.get("effective_top_k")
    if kreq is not None or effk is not None:
        du.print_stat("Top-k (requested / effective)", f"{kreq if kreq is not None else '—'} / {effk if effk is not None else '—'}")
    vf = manifest.get("vendor_fallback_used")
    if vf is not None:
        du.print_stat("Vendor width fallback used (run)", "Yes" if vf else "No")

    du.print_stat("Profile ID", str(pp.get("profile_id", "—")))
    du.print_stat("Type slug filter", str(pp.get("type_slug_filter") if pp.get("type_slug_filter") is not None else "— (all)"))

    gates = pp.get("cohort_gates") if isinstance(pp.get("cohort_gates"), dict) else {}
    if gates:
        gate_parts = [
            f"n>={gates.get('min_samples_per_family', '—')}",
            f"mapped_family={'yes' if gates.get('require_mapped_family', True) else 'no'}",
            f"sha256={'yes' if gates.get('require_sha256', True) else 'no'}",
            (
                f"missing_package={'yes' if gates.get('allow_missing_package_name', True) else 'no'}"
                f" <= {gates.get('max_missing_package_pct', '—')}%"
            ),
            f"exclude_unknown_type={'yes' if gates.get('exclude_unknown_type_slug') else 'no'}",
        ]
        du.print_stat("Cohort gates", "; ".join(gate_parts))
        excl = gates.get("exclude_families")
        if isinstance(excl, list):
            du.print_stat("Excluded families", f"{len(excl)} family name(s)")
        elif excl:
            du.print_stat("Excluded families", str(excl))
        tw0 = str(gates.get("time_window_start_utc") or "").strip()
        tw1 = str(gates.get("time_window_end_utc") or "").strip()
        if tw0 or tw1:
            du.print_stat("Cohort time window", f"{tw0 or '—'} → {tw1 or '—'}")
    else:
        du.print_stat("Cohort gates", "— (none in profile)")

    df = pp.get("dataset_filters") if isinstance(pp.get("dataset_filters"), dict) else {}
    if df:
        du.print_stat("Dataset mode", str(df.get("mode", "—")))

    topk_policy_parts = [
        f"requested={pp.get('top_k_requested', '—')}",
        f"adaptive={'yes' if bool(pp.get('allow_adaptive_top_k')) else 'no'}",
        f"vendor_width_fallback={'yes' if bool(pp.get('allow_vendor_fallback_for_width')) else 'no'}",
        f"exclude_unknown_main={'yes' if bool(pp.get('exclude_unknown_from_main_results')) else 'no'}",
    ]
    du.print_stat("Top-k policy", "; ".join(topk_policy_parts))

    flags = pp.get("feature_flags") if isinstance(pp.get("feature_flags"), dict) else {}
    if flags:
        du.print_stat(
            "Feature flags",
            _compact_kv_map(
                {k: flags[k] for k in sorted(flags.keys()) if k.startswith(("enable_", "confusion_matrix"))},
                max_keys=20,
            ),
        )
    else:
        du.print_stat("Feature flags", "—")

    po = pp.get("parser_overrides") if isinstance(pp.get("parser_overrides"), dict) else {}
    du.print_stat("Parser overrides", _compact_kv_map(po))

    ro = pp.get("runtime_overrides") if isinstance(pp.get("runtime_overrides"), dict) else {}
    du.print_stat("Runtime overrides", _compact_kv_map(ro))

    raw_models = pp.get("model_list")
    if isinstance(raw_models, list) and raw_models:
        du.print_stat("Models", ", ".join(str(m) for m in raw_models[:12]) + (" …" if len(raw_models) > 12 else ""))
    elif raw_models is not None:
        du.print_stat("Models", str(raw_models))
    print(
        "[PROFILE] Tunables: profiles/*.yaml "
        "(cohort_gates, parser_overrides, runtime_overrides, feature_flags)"
    )
    print("[ACTION] Rerun the pipeline after profile edits.")
    print("")


def show_profile_tuning_snapshot() -> int:
    """Print only the profile / pipeline tuning block for the latest resolved manifest."""
    shared = build_operator_state()
    manifest = shared.get("manifest_payload") if isinstance(shared.get("manifest_payload"), dict) else {}
    resolved_run_id = str(shared.get("resolved_run_id", "") or "")
    manifest_path = shared.get("manifest_path")
    canonical_manifest_path = shared.get("canonical_manifest_path")
    if not manifest:
        du.print_warning("[RUN] Latest run manifest could not be resolved.")
        return 1
    run_id = str(resolved_run_id or manifest.get("run_id", "unknown"))
    if resolved_run_id and isinstance(canonical_manifest_path, Path):
        manifest_path = canonical_manifest_path
    du.print_section("Pipeline profile tuning")
    du.print_stat("Resolved run ID", run_id)
    du.print_stat("Manifest path", du.format_console_path(manifest_path))
    print_profile_tuning_from_manifest(manifest)
    return 0


def show_latest_run_snapshot() -> int:
    """Print a concise snapshot of the latest run manifest."""
    du.print_section("Current Run Summary")
    shared = build_operator_state()
    manifest = shared.get("manifest_payload") if isinstance(shared.get("manifest_payload"), dict) else {}
    resolved_run_id = str(shared.get("resolved_run_id", "") or "")
    manifest_path = shared.get("manifest_path")
    if not manifest:
        du.print_warning("[RUN] Latest run manifest could not be resolved.")
        return 1

    run_id = str(resolved_run_id or manifest.get("run_id", "unknown"))
    run_root = shared.get("run_root") if isinstance(shared.get("run_root"), Path) else resolve_run_root_for_manifest(
        manifest,
        run_id=run_id,
        manifest_path=manifest_path,
    )
    canonical_manifest_path = (
        shared.get("canonical_manifest_path")
        if isinstance(shared.get("canonical_manifest_path"), Path)
        else run_root / "run_manifest.json"
    )
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
    du.print_stat("Publication-ready Status", str(shared.get("publication_ready_status", "") or "unknown"))
    du.print_stat("Cohort Lock Status", str(shared.get("cohort_lock_status", "") or "unknown"))
    taxonomy_drift = taxonomy_label_drift_display(manifest)
    if taxonomy_drift:
        du.print_stat("Taxonomy Drift", taxonomy_drift)
    du.print_stat("Cohort Methodology", cohort_methodology_summary(shared))
    du.print_stat("Pipeline Runtime (sec)", runtime_display)
    du.print_stat("Top Model", top_model)
    du.print_stat("Top Macro F1", top_macro)
    du.print_stat(
        "Run Manifest",
        du.format_console_path(canonical_manifest_path if canonical_manifest_path.exists() else manifest_path),
    )
    print_profile_tuning_from_manifest(manifest)
    return 0


def show_recent_runs_overview(limit: int = 10, *, include_noncanonical: bool = False) -> int:
    """Show a compact table of recent run manifests."""
    title = "Recent Run History"
    if include_noncanonical:
        title = "Full Run Folder History"
    du.print_section(title)
    output_root = canonical_output_root()
    runs_root = output_root / "runs"
    if not runs_root.exists():
        du.print_warning(f"[RUN] Runs directory not found: {du.format_console_path(runs_root)}")
        return 1

    rows: list[dict[str, object]] = []
    for run_dir in runs_root.iterdir():
        if not run_dir.is_dir():
            continue
        manifest_path = run_dir / "run_manifest.json"
        manifest = read_json_object(manifest_path)
        if not manifest:
            continue
        shared = build_operator_state(output_base=output_root, run_id=run_dir.name)
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
                "publication_ready_status": str(shared.get("publication_ready_status", "") or "unknown"),
                "cohort_lock_status": str(shared.get("cohort_lock_status", "") or "unknown"),
                "cohort_methodology": cohort_methodology_summary(shared),
                "timestamp_utc": str(
                    run_summary.get("timestamp_utc", manifest.get("timestamp_utc", ""))
                ),
                "__sort_key": candidate_sort_key(run_id=run_id, manifest_payload=manifest),
            }
        )

    if not rows:
        du.print_warning("[RUN] No run-scoped manifests found under output/runs.")
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
        print(
            f"[RUN] Hidden {hidden_noncanonical_count} non-canonical run folder(s); "
            "use Full Run Folder History to inspect them."
        )
    print("[DIAGNOSTICS] Deep validation: Diagnostics > Run Health Check for Specific Run ID")
    return 0


def show_session_and_output_details() -> int:
    """Print active session and output-routing details."""
    du.print_section("Session and Output Details")
    shared = build_operator_state()
    output_root = (
        shared.get("output_root")
        if isinstance(shared.get("output_root"), Path)
        else canonical_output_root()
    )
    latest_run_id = str(shared.get("latest_run_id", "") or "None yet")
    locked_run_id = str(shared.get("locked_run_id", "") or "(none)")
    latest_profile_id = str(shared.get("profile_id", "") or "Unknown")
    manifest = shared.get("manifest_payload") if isinstance(shared.get("manifest_payload"), dict) else {}
    manifest_path = shared.get("manifest_path")
    run_root = shared.get("run_root") if isinstance(shared.get("run_root"), Path) else Path()
    canonical_manifest_path = (
        shared.get("canonical_manifest_path")
        if isinstance(shared.get("canonical_manifest_path"), Path)
        else run_root / "run_manifest.json"
    )

    du.print_stat("Environment", "Fedora Local Research")
    du.print_stat("Output Root", str(output_root))
    du.print_stat("Artifact Mode", "Run-scoped")
    du.print_stat("Latest Run", latest_run_id)
    du.print_stat("Latest Profile", latest_profile_id)
    du.print_stat("Locked Evidence Run", locked_run_id)
    du.print_stat(
        "Publication Exports",
        "Yes" if bool(shared.get("has_publication_exports", False)) else "No",
    )
    du.print_stat("Publication-ready Status", str(shared.get("publication_ready_status", "") or "unknown"))
    du.print_stat("Cohort Lock Status", str(shared.get("cohort_lock_status", "") or "unknown"))
    du.print_stat("Cohort Methodology", cohort_methodology_summary(shared))
    du.print_stat("Run Diagnostics Available", "Yes" if bool(shared.get("latest_run_has_diagnostics", False)) else "No")
    du.print_stat("Run-Scoped Provenance", "Yes" if bool(shared.get("latest_run_has_provenance", False)) else "No")
    best_index_path = shared.get("best_run_index_path")
    if isinstance(best_index_path, Path) and best_index_path:
        du.print_stat("Best Run Index", du.format_console_path(best_index_path))
    if manifest:
        du.print_stat(
            "Resolved Manifest",
            du.format_console_path(canonical_manifest_path if canonical_manifest_path.exists() else manifest_path),
        )
    return 0
