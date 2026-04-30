"""Tests for governance integrity path enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from analysis.pipeline.governance.exceptions import IntegrityStop
from analysis.pipeline.governance.integrity import (
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

