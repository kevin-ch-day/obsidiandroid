"""Tests for canonical output path helpers."""

from __future__ import annotations

from pathlib import Path

from config import app_config
from utils import output_paths


def test_resolve_runtime_run_directory_uses_layout_when_no_runtime_root(
    monkeypatch, tmp_path: Path
) -> None:
    """Without RUNTIME_RUN_ROOT, resolve under output_root/runs/<run_id>."""
    out = tmp_path / "output"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ROOT", "", raising=False)
    rid = "run123"
    expected = out / "runs" / rid
    assert output_paths.resolve_runtime_run_directory(rid) == expected.resolve()


def test_resolve_runtime_run_directory_prefers_runtime_run_root(
    monkeypatch, tmp_path: Path
) -> None:
    """Evidence-style runs point DEFAULT_OUTPUT_DIR at the run folder; avoid double runs/."""
    rid = "run123"
    run_root = tmp_path / "output" / "runs" / rid
    run_root.mkdir(parents=True)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ROOT", str(run_root), raising=False)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(run_root), raising=False)
    assert output_paths.resolve_runtime_run_directory(rid) == run_root.resolve()
