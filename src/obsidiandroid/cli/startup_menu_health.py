"""Run health check actions for the startup menu."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from obsidiandroid.cli.ui import display as du
from obsidiandroid.common.output_paths import output_root as canonical_output_root
from obsidiandroid.governance.evidence_mode_resolver import coalesce_manifest_publication_mode

from .startup_menu_run_context import (
    read_json_object,
    read_run_summary,
    resolve_latest_manifest_payload,
    resolve_manifest_for_run_id,
    resolve_run_root_for_manifest,
)
from obsidiandroid.diagnostics import reproducibility_workbench as repro_workbench

def run_health_check(*, run_id: str | None = None) -> int:
    """Run health + artifact checks for latest or selected run (writes run-scoped diagnostics)."""
    du.print_section("Run Health & Artifact Check")
    output_root = canonical_output_root()
    diagnostics_dir = output_root / "diagnostics"
    latest_manifest_path = diagnostics_dir / "run_manifest.latest.json"

    manifest_rows: list[dict[str, str]] = []

    def _add_manifest_check(name: str, status: str, detail: str, *, plain: str = "", bucket: str = "manifest") -> None:
        manifest_rows.append(
            {
                "check": name,
                "status": status.upper().strip(),
                "detail": detail,
                "plain_language": plain,
                "bucket": bucket,
            }
        )

    requested_run_id = (run_id or "").strip() or None
    latest_payload = read_json_object(latest_manifest_path)
    resolved_run_id: str | None = None
    canonical_manifest: dict = {}
    canonical_manifest_path: Path | None = None

    if requested_run_id:
        canonical_manifest, canonical_manifest_path = resolve_manifest_for_run_id(requested_run_id)
        if canonical_manifest:
            resolved_run_id = str(canonical_manifest.get("run_id", "")).strip() or requested_run_id
            _add_manifest_check("selected_run_manifest_exists", "PASS", str(canonical_manifest_path))
        else:
            _add_manifest_check(
                "selected_run_manifest_exists",
                "FAIL",
                f"Missing canonical manifest for run_id={requested_run_id}: {canonical_manifest_path}",
            )
    else:
        if not latest_payload:
            _add_manifest_check("latest_manifest_exists", "FAIL", f"Missing or unreadable {latest_manifest_path}")
        else:
            _add_manifest_check("latest_manifest_exists", "PASS", str(latest_manifest_path))
            canonical_manifest, resolved_run_id, canonical_manifest_path = resolve_latest_manifest_payload()
            if canonical_manifest_path != latest_manifest_path and canonical_manifest:
                _add_manifest_check("canonical_manifest_exists", "PASS", str(canonical_manifest_path))

    if not canonical_manifest:
        du.print_table(
            [{"check": r["check"], "status": r["status"], "detail": r["detail"]} for r in manifest_rows],
            title="Run health checks",
            show_index=False,
        )
        du.print_error("[RUN] Health check failed (no manifest).")
        return 1

    effective_run_id = requested_run_id or resolved_run_id or str(canonical_manifest.get("run_id", "")).strip()
    if effective_run_id:
        _add_manifest_check("run_id_present", "PASS", effective_run_id)
    else:
        _add_manifest_check("run_id_present", "FAIL", "run_id missing in manifest payload.")

    canonical_run_id = str(canonical_manifest.get("run_id", "")).strip()
    if effective_run_id and canonical_run_id and effective_run_id != canonical_run_id:
        _add_manifest_check(
            "manifest_run_id_consistent",
            "FAIL",
            f"requested/latest run_id={effective_run_id} differs from canonical run_id={canonical_run_id}.",
        )
    else:
        _add_manifest_check(
            "manifest_run_id_consistent", "PASS", canonical_run_id or effective_run_id or "n/a"
        )

    run_root_dir = resolve_run_root_for_manifest(
        canonical_manifest if isinstance(canonical_manifest, dict) else {},
        run_id=effective_run_id or None,
        manifest_path=canonical_manifest_path,
    ) if effective_run_id else Path()
    run_summary = read_run_summary(run_root_dir) if run_root_dir.exists() else {}

    timestamp_utc = str(
        canonical_manifest.get("timestamp_utc", "") or latest_payload.get("created_at_utc", "")
    ).strip()

    fs_rows, _, _ = repro_workbench.build_filesystem_artifact_checks(
        output_root=output_root,
        effective_run_id=effective_run_id or "",
        canonical_manifest=canonical_manifest,
        run_root=run_root_dir,
        run_summary=run_summary,
        timestamp_source=timestamp_utc,
    )
    all_rows = manifest_rows + fs_rows

    def _count(rows: list[dict[str, str]]) -> tuple[int, int, int]:
        p = sum(1 for r in rows if str(r.get("status")) == "PASS")
        w = sum(1 for r in rows if str(r.get("status")) == "WARN")
        f = sum(1 for r in rows if str(r.get("status")) == "FAIL")
        return p, w, f

    pass_count, warn_count, fail_count = _count(all_rows)

    ev_on = coalesce_manifest_publication_mode(canonical_manifest)
    profile_id = str(
        run_summary.get("profile_id") or (canonical_manifest.get("profile_params") or {}).get("profile_id") or ""
    )
    run_status = str(run_summary.get("run_status") or canonical_manifest.get("run_status") or "unknown")

    if fail_count:
        interpretation = "Resolve failing checks before trusting artifacts from this run."
    elif not ev_on:
        interpretation = (
            "This run is development-research healthy. It is not an evidence-locked paper run."
        )
    else:
        interpretation = (
            "Evidence-oriented manifest flags are set — validate publication bundles and compliance exports separately."
        )

    report_run_id = effective_run_id or "unknown"
    diagnostics_out = run_root_dir / "diagnostics" if run_root_dir.exists() else diagnostics_dir
    payload = {
        "meta": {
            "run_id": report_run_id,
            "profile_id": profile_id,
            "run_status": run_status,
            "run_root": str(run_root_dir),
            "evidence_mode_resolved": ev_on,
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": {"pass": pass_count, "warn": warn_count, "fail": fail_count},
        "checks": all_rows,
        "interpretation": interpretation,
    }
    md_path, json_path = repro_workbench.write_run_health_artifact_reports(
        diagnostics_out_dir=diagnostics_out,
        payload=payload,
    )

    legacy_payload = {
        "run_id": report_run_id,
        "generated_at_utc": payload["generated_at_utc"],
        "summary": payload["summary"],
        "checks": [{"check": r["check"], "status": r["status"], "detail": r["detail"]} for r in all_rows],
    }
    report_latest = diagnostics_dir / "quick_health_check.latest.json"
    report_run = diagnostics_dir / f"quick_health_check_{report_run_id}.json"
    report_latest.write_text(json.dumps(legacy_payload, indent=2), encoding="utf-8")
    report_run.write_text(json.dumps(legacy_payload, indent=2), encoding="utf-8")

    print("")
    print("RUN HEALTH & ARTIFACT CHECK")
    print("---------------------------")
    du.print_stat("Run ID", report_run_id)
    du.print_stat("Status", run_status)
    du.print_stat("Profile", profile_id or "n/a")
    du.print_stat("Run root", du.format_console_path(run_root_dir))
    print("")
    du.print_stat("Health PASS", str(pass_count))
    du.print_stat("Health WARN", str(warn_count))
    du.print_stat("Health FAIL", str(fail_count))
    print("")
    du.print_table(
        [{"check": r["check"], "status": r["status"], "detail": r["detail"]} for r in all_rows],
        title="Checks",
        show_index=False,
    )
    warn_plain = [r for r in all_rows if str(r.get("status")) == "WARN" and str(r.get("plain_language") or "").strip()]
    if warn_plain:
        print("")
        du.print_subheader("Warnings (plain language)")
        for r in warn_plain:
            du.print_warning(f"{r['check']}: {r['plain_language']}")
    print("")
    print(f"[DIAGNOSTICS] {du.format_console_path(json_path)}")
    print(f"[DIAGNOSTICS] {du.format_console_path(md_path)}")
    print(f"[DIAGNOSTICS] Legacy mirror:{du.format_console_path(report_run)}")
    print("")
    print(f"[RUN] Health summary: PASS={pass_count}, WARN={warn_count}, FAIL={fail_count}")
    print(f"[RUN] Interpretation: {interpretation}")

    if fail_count:
        du.print_error("[RUN] Health check failed.")
        return 1
    if warn_count:
        du.print_warning("[RUN] Health check passed with warnings.")
        return 0
    print("[RUN] Health check passed.")
    return 0
