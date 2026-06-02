"""Tests for run capsule lifecycle dotfiles."""

from __future__ import annotations

import json
from pathlib import Path

from obsidiandroid.common.run_lifecycle import (
    find_active_profile_runs,
    finalize_run_lifecycle_terminal,
    mark_run_lifecycle_running,
)
from obsidiandroid.pipeline import run_bounds


def test_lifecycle_running_then_complete(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "rid1"
    mark_run_lifecycle_running(
        run_root,
        run_id="rid1",
        profile_id="android_malware_all_current",
    )
    assert (run_root / ".RUNNING").is_file()
    assert not (run_root / ".COMPLETE").exists()
    running_payload = json.loads((run_root / ".RUNNING").read_text(encoding="utf-8"))
    assert running_payload["run_id"] == "rid1"
    assert running_payload["profile_id"] == "android_malware_all_current"
    assert isinstance(running_payload.get("pid"), int)
    assert str(running_payload.get("hostname", "")).strip()

    ctx: dict = {"run_status": "complete", "completed_stage": "manifest"}
    finalize_run_lifecycle_terminal(run_root, manifest_context=ctx, manifest_stage_result_code=0)
    assert not (run_root / ".RUNNING").exists()
    assert (run_root / ".COMPLETE").is_file()
    assert ctx.get("lifecycle_state") == "complete"
    assert ctx.get("lifecycle_finished_at_utc")


def test_lifecycle_failed_on_interrupt_status(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "rid2"
    mark_run_lifecycle_running(run_root, run_id="rid2")
    ctx = {"run_status": "interrupted", "failure_reason": "KeyboardInterrupt"}
    finalize_run_lifecycle_terminal(run_root, manifest_context=ctx, manifest_stage_result_code=0)
    assert (run_root / ".FAILED").is_file()
    assert not (run_root / ".RUNNING").exists()
    assert ctx.get("lifecycle_state") == "interrupted"


def test_find_active_profile_runs_returns_live_peer_for_current_pid(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "rid3"
    mark_run_lifecycle_running(
        run_root,
        run_id="rid3",
        profile_id="android_malware_all_current",
    )

    peers = find_active_profile_runs(
        tmp_path / "output",
        profile_id="android_malware_all_current",
    )

    assert len(peers) == 1
    assert peers[0].run_id == "rid3"
    assert peers[0].profile_id == "android_malware_all_current"


def test_find_active_profile_runs_ignores_dead_same_host_pid(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "rid4"
    mark_run_lifecycle_running(
        run_root,
        run_id="rid4",
        profile_id="android_malware_all_current",
    )
    payload = json.loads((run_root / ".RUNNING").read_text(encoding="utf-8"))
    payload["pid"] = 99999999
    (run_root / ".RUNNING").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    peers = find_active_profile_runs(
        tmp_path / "output",
        profile_id="android_malware_all_current",
    )

    assert peers == []


def test_merge_lifecycle_into_run_summaries(tmp_path: Path, monkeypatch) -> None:
    from config import app_config
    from obsidiandroid.pipeline.manifest.stage_manifest_writers import (
        merge_lifecycle_fields_into_run_summaries,
    )

    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(tmp_path / "output"), raising=False)
    run_capsule = tmp_path / "output" / "runs" / "rmerge"
    diag = run_capsule / "diagnostics"
    diag.mkdir(parents=True)
    run_id = "rmerge"
    base = {"schema_version": "1.0", "run_id": run_id}
    (run_capsule / "run_summary.json").write_text(json.dumps(base), encoding="utf-8")
    (diag / f"run_summary_{run_id}.json").write_text(json.dumps(base), encoding="utf-8")
    gdiag = tmp_path / "output" / "diagnostics"
    gdiag.mkdir(parents=True, exist_ok=True)
    (gdiag / "run_summary.latest.json").write_text(json.dumps(base), encoding="utf-8")

    ctx = {
        "lifecycle_state": "complete",
        "lifecycle_finished_at_utc": "2026-01-01T00:00:00+00:00",
    }
    merge_lifecycle_fields_into_run_summaries(
        run_root=run_capsule,
        diagnostics_dir=diag,
        run_id=run_id,
        manifest_context=ctx,
    )
    disk = json.loads((run_capsule / "run_summary.json").read_text(encoding="utf-8"))
    assert disk["lifecycle_state"] == "complete"
    assert "lifecycle_finished_at_utc" in disk


def test_run_bounds_lifecycle() -> None:
    """run_bounds module should preserve lifecycle capsules through set/get/clear."""
    assert run_bounds.get_pipeline_run_bounds() is None
    b = run_bounds.PipelineRunBounds(
        run_id="rid",
        profile_ref="p",
        stop_after="full",
        diagnostics_dir=Path("/tmp/diag"),
        output_root_base=Path("/tmp/out"),
        runtime_run_root=Path("/tmp/out/runs/rid"),
    )
    run_bounds.set_pipeline_run_bounds(b)
    assert run_bounds.get_pipeline_run_bounds() is b
    run_bounds.clear_pipeline_run_bounds()
    assert run_bounds.get_pipeline_run_bounds() is None
