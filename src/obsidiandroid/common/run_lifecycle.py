"""Run capsule lifecycle dotfiles under ``output/runs/<run_id>/``.

Humans and shell tools can read ``.RUNNING`` / ``.COMPLETE`` / ``.FAILED`` at a
glance. Structured status remains authoritative in ``run_manifest.json`` and
``run_summary.json`` (written during manifest finalization).
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MARKER_RUNNING = ".RUNNING"
_MARKER_COMPLETE = ".COMPLETE"
_MARKER_FAILED = ".FAILED"


@dataclass(frozen=True)
class ActiveRunRecord:
    """Summary of an active run discovered from a ``.RUNNING`` marker."""

    run_id: str
    run_root: Path
    profile_id: str
    pid: int | None
    hostname: str
    started_at_utc: str
    marker_path: Path


def _load_marker_json(path: Path) -> dict[str, Any]:
    """Best-effort marker JSON loader."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _pid_is_alive(pid: int) -> bool:
    """Return ``True`` when ``pid`` currently exists on this host."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def mark_run_lifecycle_running(
    run_root: Path,
    *,
    run_id: str | None = None,
    profile_id: str | None = None,
) -> None:
    """Create ``.RUNNING`` and remove stale terminal markers from a prior crash."""
    run_root.mkdir(parents=True, exist_ok=True)
    for name in (_MARKER_COMPLETE, _MARKER_FAILED):
        p = run_root / name
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    payload = {
        "state": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "run_id": str(run_id or run_root.name),
        "profile_id": str(profile_id or "").strip(),
    }
    (run_root / _MARKER_RUNNING).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def find_active_profile_runs(
    output_root: Path,
    *,
    profile_id: str,
    exclude_run_id: str = "",
) -> list[ActiveRunRecord]:
    """Return active runs for the requested profile based on live ``.RUNNING`` markers."""
    runs_root = output_root / "runs"
    if not runs_root.is_dir():
        return []
    wanted_profile = str(profile_id or "").strip().lower()
    current_host = socket.gethostname()
    active: list[ActiveRunRecord] = []
    for run_dir in sorted(runs_root.iterdir()):
        if not run_dir.is_dir():
            continue
        marker_path = run_dir / _MARKER_RUNNING
        if not marker_path.is_file():
            continue
        payload = _load_marker_json(marker_path)
        marker_profile = str(payload.get("profile_id", "") or "").strip().lower()
        marker_run_id = str(payload.get("run_id", "") or run_dir.name).strip()
        if exclude_run_id and marker_run_id == exclude_run_id:
            continue
        if marker_profile != wanted_profile:
            continue
        marker_pid = payload.get("pid")
        pid = int(marker_pid) if isinstance(marker_pid, int) else None
        hostname = str(payload.get("hostname", "") or "").strip()
        same_host = not hostname or hostname == current_host
        if same_host and (pid is None or not _pid_is_alive(pid)):
            continue
        active.append(
            ActiveRunRecord(
                run_id=marker_run_id,
                run_root=run_dir,
                profile_id=marker_profile or wanted_profile,
                pid=pid,
                hostname=hostname or current_host,
                started_at_utc=str(payload.get("started_at_utc", "") or ""),
                marker_path=marker_path,
            )
        )
    return active


def finalize_run_lifecycle_terminal(
    run_root: Path,
    *,
    manifest_context: dict[str, Any],
    manifest_stage_result_code: int,
) -> None:
    """Replace ``.RUNNING`` with a terminal marker from ``manifest_context`` / manifest result."""
    running = run_root / _MARKER_RUNNING
    if running.is_file():
        try:
            running.unlink()
        except OSError:
            pass

    rs = str(manifest_context.get("run_status", "") or "").strip().lower()
    reason = str(
        manifest_context.get("failure_reason", "")
        or manifest_context.get("integrity_error", "")
        or ""
    ).strip()
    finished = datetime.now(timezone.utc).isoformat()
    manifest_context["lifecycle_finished_at_utc"] = finished

    if rs in ("failed", "interrupted"):
        manifest_context["lifecycle_state"] = rs
        body = {"state": rs, "finished_at_utc": finished, "failure_reason": reason or None}
        (run_root / _MARKER_FAILED).write_text(
            json.dumps(body, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return

    if manifest_stage_result_code != 0:
        manifest_context["lifecycle_state"] = "failed"
        body = {
            "state": "failed",
            "finished_at_utc": finished,
            "failure_reason": "manifest_stage_nonzero_exit",
        }
        (run_root / _MARKER_FAILED).write_text(
            json.dumps(body, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return

    if rs == "partial":
        manifest_context["lifecycle_state"] = "partial"
    else:
        manifest_context["lifecycle_state"] = "complete"

    body = {
        "state": manifest_context["lifecycle_state"],
        "finished_at_utc": finished,
        "completed_stage": str(manifest_context.get("completed_stage", "") or "").strip() or None,
    }
    (run_root / _MARKER_COMPLETE).write_text(
        json.dumps(body, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "ActiveRunRecord",
    "find_active_profile_runs",
    "finalize_run_lifecycle_terminal",
    "mark_run_lifecycle_running",
]
