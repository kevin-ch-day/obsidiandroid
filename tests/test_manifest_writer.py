"""Tests for atomic manifest writer behavior."""

from __future__ import annotations

import json
from pathlib import Path

from analysis.pipeline.manifest.writer import write_manifest_atomic


def test_write_manifest_atomic_creates_file(tmp_path: Path) -> None:
    """Atomic writer should create manifest file with expected payload."""
    target = tmp_path / "run_manifest.json"
    payload = {"run_id": "r1", "value": 1}
    out = write_manifest_atomic(target_path=target, payload=payload)
    assert out == target
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data == payload


def test_write_manifest_atomic_replaces_existing_file(tmp_path: Path) -> None:
    """Atomic writer should replace existing target content."""
    target = tmp_path / "run_manifest.json"
    target.write_text('{"run_id":"old"}', encoding="utf-8")
    payload = {"run_id": "new", "value": 2}
    write_manifest_atomic(target_path=target, payload=payload)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["run_id"] == "new"
    assert data["value"] == 2

