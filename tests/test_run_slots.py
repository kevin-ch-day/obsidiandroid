"""Tests for slot-based runtime run planning."""

from __future__ import annotations

import json
from pathlib import Path

from obsidiandroid.common import run_slots
from obsidiandroid.orchestration import runtime_reporting


def test_resolve_run_slot_plan_maps_major_family_profile() -> None:
    plan = run_slots.resolve_run_slot_plan(
        profile_id="android_malware_major_families",
        paper_locked=False,
        evidence_mode=False,
        keep_run_output=False,
    )

    assert plan.run_slot == "majorfam_benchmark"
    assert plan.run_mode == "benchmark"
    assert plan.claim_surface == "governed_major_family_benchmark"
    assert plan.archive_run is False


def test_prepare_run_root_replaces_normal_slot_and_archives_failed_run(tmp_path: Path) -> None:
    runs_root = tmp_path / "output" / "runs"
    slot_root = runs_root / "majorfam_benchmark"
    slot_root.mkdir(parents=True, exist_ok=True)
    (slot_root / "stale.txt").write_text("x", encoding="utf-8")
    (slot_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260601T010101Z__old001",
                "run_status": "failed",
                "run_started_at_utc": "2026-06-01T01:01:01+00:00",
            }
        ),
        encoding="utf-8",
    )

    prepared = run_slots.prepare_run_root(
        runs_root=runs_root,
        run_slot="majorfam_benchmark",
        run_instance_id="20260602T010101Z__new001",
        archive_run=False,
        keep_last_failed_runs=1,
    )

    assert Path(prepared["run_root"]) == slot_root
    assert (slot_root / "diagnostics").is_dir()
    assert not (slot_root / "stale.txt").exists()
    archived = runs_root / "_archived" / "failed" / "majorfam_benchmark" / "20260601T010101Z__old001"
    assert archived.is_dir()
    assert (archived / "run_manifest.json").is_file()


def test_prepare_run_root_archives_previous_completed_slot_with_bounded_retention(tmp_path: Path) -> None:
    runs_root = tmp_path / "output" / "runs"
    slot_root = runs_root / "majorfam_benchmark"
    slot_root.mkdir(parents=True, exist_ok=True)
    (slot_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260601T010101Z__complete1",
                "run_status": "complete",
                "run_started_at_utc": "2026-06-01T01:01:01+00:00",
            }
        ),
        encoding="utf-8",
    )
    (slot_root / "metrics.csv").write_text("metric,value\nmacro_f1,0.9\n", encoding="utf-8")

    prepared = run_slots.prepare_run_root(
        runs_root=runs_root,
        run_slot="majorfam_benchmark",
        run_instance_id="20260602T010101Z__new001",
        archive_run=False,
        keep_last_completed_runs=1,
    )

    archived = runs_root / "_archived" / "completed" / "majorfam_benchmark" / "20260601T010101Z__complete1"
    assert prepared["cleanup_action"] == "archived_completed_slot"
    assert prepared["previous_slot_archive"] == archived
    assert archived.is_dir()
    assert (archived / "metrics.csv").is_file()
    assert Path(prepared["run_root"]) == slot_root


def test_prepare_run_root_archives_complete_marker_when_manifest_status_stale(tmp_path: Path) -> None:
    runs_root = tmp_path / "output" / "runs"
    slot_root = runs_root / "allcurrent_diagnostic"
    slot_root.mkdir(parents=True, exist_ok=True)
    (slot_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260601T010101Z__stale1",
                "run_status": "running",
                "run_started_at_utc": "2026-06-01T01:01:01+00:00",
            }
        ),
        encoding="utf-8",
    )
    (slot_root / ".COMPLETE").write_text("ok\n", encoding="utf-8")
    (slot_root / "research.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    prepared = run_slots.prepare_run_root(
        runs_root=runs_root,
        run_slot="allcurrent_diagnostic",
        run_instance_id="20260602T010101Z__new001",
        archive_run=False,
        keep_last_completed_runs=1,
    )

    archived = (
        runs_root / "_archived" / "completed" / "allcurrent_diagnostic" / "20260601T010101Z__stale1"
    )
    assert prepared["cleanup_action"] == "archived_completed_slot_via_marker"
    assert prepared["previous_slot_archive"] == archived
    assert (archived / "research.csv").is_file()
    assert Path(prepared["run_root"]) == slot_root


def test_prepare_run_root_retains_three_completed_archives(tmp_path: Path) -> None:
    runs_root = tmp_path / "output" / "runs"
    completed = runs_root / "_archived" / "completed" / "allcurrent_diagnostic"
    completed.mkdir(parents=True, exist_ok=True)
    for idx, stamp in enumerate(
        ("20260601T010101Z__old1", "20260602T010101Z__old2", "20260603T010101Z__old3"),
        start=1,
    ):
        prior = completed / stamp
        prior.mkdir()
        (prior / "run_manifest.json").write_text(
            json.dumps(
                {
                    "run_id": stamp,
                    "run_status": "complete",
                    "run_started_at_utc": f"2026-06-0{idx}T01:01:01+00:00",
                }
            ),
            encoding="utf-8",
        )

    slot_root = runs_root / "allcurrent_diagnostic"
    slot_root.mkdir(parents=True, exist_ok=True)
    (slot_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260604T010101Z__live",
                "run_status": "complete",
                "run_started_at_utc": "2026-06-04T01:01:01+00:00",
            }
        ),
        encoding="utf-8",
    )

    run_slots.prepare_run_root(
        runs_root=runs_root,
        run_slot="allcurrent_diagnostic",
        run_instance_id="20260605T010101Z__new",
        archive_run=False,
        keep_last_completed_runs=3,
    )

    kept = sorted(p.name for p in completed.iterdir() if p.is_dir())
    assert kept == [
        "20260602T010101Z__old2",
        "20260603T010101Z__old3",
        "20260604T010101Z__live",
    ]


def test_prepare_run_root_failed_retention_is_per_slot(tmp_path: Path) -> None:
    runs_root = tmp_path / "output" / "runs"
    # Pre-seed a failed archive for a different slot; it must survive pruning.
    other = runs_root / "_archived" / "failed" / "allcurrent_diagnostic" / "20260601T010101Z__other"
    other.mkdir(parents=True)
    (other / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260601T010101Z__other",
                "run_status": "failed",
                "run_started_at_utc": "2026-06-01T01:01:01+00:00",
            }
        ),
        encoding="utf-8",
    )

    slot_root = runs_root / "majorfam_benchmark"
    slot_root.mkdir(parents=True, exist_ok=True)
    (slot_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260602T010101Z__fail1",
                "run_status": "failed",
                "run_started_at_utc": "2026-06-02T01:01:01+00:00",
            }
        ),
        encoding="utf-8",
    )

    run_slots.prepare_run_root(
        runs_root=runs_root,
        run_slot="majorfam_benchmark",
        run_instance_id="20260603T010101Z__new",
        archive_run=False,
        keep_last_failed_runs=1,
    )

    assert other.is_dir()
    archived = runs_root / "_archived" / "failed" / "majorfam_benchmark" / "20260602T010101Z__fail1"
    assert archived.is_dir()


def test_setup_runtime_context_uses_slot_run_root(monkeypatch, tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    monkeypatch.setattr(runtime_reporting.app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(runtime_reporting.app_config, "RUNTIME_RUN_ROOT", "", raising=False)

    result = runtime_reporting.setup_runtime_context(
        run_id="20260602T010101Z__abc123",
        run_slot="majorfam_benchmark",
        archive_run=False,
    )

    assert result["runtime_run_root"] == output_root / "runs" / "majorfam_benchmark"
    assert result["run_slot"] == "majorfam_benchmark"
    assert (output_root / "runs" / "majorfam_benchmark" / "diagnostics").is_dir()


def test_setup_runtime_context_archives_keep_runs(monkeypatch, tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    monkeypatch.setattr(runtime_reporting.app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)

    result = runtime_reporting.setup_runtime_context(
        run_id="20260602T010101Z__keep01",
        run_slot="majorfam_benchmark",
        archive_run=True,
    )

    assert result["runtime_run_root"] == output_root / "runs" / "_archived" / "kept" / "20260602T010101Z__keep01"
    assert (Path(result["runtime_run_root"]) / "diagnostics").is_dir()
