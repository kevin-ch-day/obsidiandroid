"""Tests for governance integrity path enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from obsidiandroid.governance.exceptions import IntegrityStop
from obsidiandroid.governance.integrity import (
    enforce_run_scoped_artifact_paths,
    validate_run_scoped_artifact_paths,
)


def test_validate_run_scoped_artifact_paths_passes_for_run_root(tmp_path: Path) -> None:
    """Validation should pass when artifacts are under run root."""
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r1"
    run_root.mkdir(parents=True, exist_ok=True)
    artifact = run_root / "diagnostics" / "ok.csv"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("x\n1\n", encoding="utf-8")
    report = validate_run_scoped_artifact_paths(
        artifact_paths=[str(artifact)],
        run_root=run_root,
        output_root=output_root,
        allow_latest=True,
    )
    assert report.passed is True
    assert report.invalid_paths == tuple()


def test_validate_run_scoped_artifact_paths_passes_for_repo_runtime_logs(tmp_path, monkeypatch) -> None:
    """Runtime tee logs live under repo logs/runtime/<run_id>/, not under output/runs/."""
    monkeypatch.setenv("OBSIDIANDROID_LOG_FILES_ROOT", str(tmp_path / "logs"))
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r1"
    run_root.mkdir(parents=True, exist_ok=True)
    tee = tmp_path / "logs" / "runtime" / "r1" / "pipeline_runtime_console_r1.log"
    tee.parent.mkdir(parents=True, exist_ok=True)
    tee.write_text("log\n", encoding="utf-8")
    report = validate_run_scoped_artifact_paths(
        artifact_paths=[str(tee)],
        run_root=run_root,
        output_root=output_root,
        allow_latest=True,
    )
    assert report.passed is True
    assert report.invalid_paths == tuple()


def test_validate_run_scoped_artifact_paths_allows_pipeline_stage_timings_latest(tmp_path: Path) -> None:
    """Global latest pointer for pipeline stage timings is an allowed operator mirror."""
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r1"
    run_root.mkdir(parents=True, exist_ok=True)
    pointer = output_root / "diagnostics" / "pipeline_stage_timings.latest.csv"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text("stage,duration_sec\nsamples,1.0\n", encoding="utf-8")
    report = validate_run_scoped_artifact_paths(
        artifact_paths=[str(pointer)],
        run_root=run_root,
        output_root=output_root,
        allow_latest=True,
    )
    assert report.passed is True
    assert report.invalid_paths == tuple()


def test_validate_run_scoped_artifact_paths_fails_for_global_path(tmp_path: Path) -> None:
    """Validation should flag non-run-scoped artifacts."""
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r1"
    run_root.mkdir(parents=True, exist_ok=True)
    bad = output_root / "diagnostics" / "bad.csv"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("x\n1\n", encoding="utf-8")
    report = validate_run_scoped_artifact_paths(
        artifact_paths=[str(bad)],
        run_root=run_root,
        output_root=output_root,
        allow_latest=False,
    )
    assert report.passed is False
    assert str(bad) in report.invalid_paths


def test_enforce_run_scoped_artifact_paths_raises_on_violation(tmp_path: Path) -> None:
    """Enforcement should raise IntegrityStop on violations."""
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r1"
    run_root.mkdir(parents=True, exist_ok=True)
    bad = output_root / "diagnostics" / "bad.csv"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("x\n1\n", encoding="utf-8")
    with pytest.raises(IntegrityStop):
        enforce_run_scoped_artifact_paths(
            artifact_paths=[str(bad)],
            run_root=run_root,
            output_root=output_root,
            allow_latest=False,
        )
