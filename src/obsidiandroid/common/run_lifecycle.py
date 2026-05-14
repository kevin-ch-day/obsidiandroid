"""Run capsule lifecycle dotfiles under ``output/runs/<run_id>/``.

Humans and shell tools can read ``.RUNNING`` / ``.COMPLETE`` / ``.FAILED`` at a
glance. Structured status remains authoritative in ``run_manifest.json`` and
``run_summary.json`` (written during manifest finalization).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MARKER_RUNNING = ".RUNNING"
_MARKER_COMPLETE = ".COMPLETE"
_MARKER_FAILED = ".FAILED"


def mark_run_lifecycle_running(run_root: Path) -> None:
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
    }
    (run_root / _MARKER_RUNNING).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
    "finalize_run_lifecycle_terminal",
    "mark_run_lifecycle_running",
]
