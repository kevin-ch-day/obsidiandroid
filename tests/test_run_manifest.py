"""Tests for dynamic run-manifest path resolution."""

from __future__ import annotations

import json
from pathlib import Path

from config import app_config
from utils import run_manifest


def test_write_run_manifest_uses_current_default_output_dir(monkeypatch, tmp_path: Path) -> None:
    """Manifest writes should follow runtime output-root overrides by default."""
    output_root = tmp_path / "output"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)

    path = run_manifest.write_run_manifest({"run_id": "r1"})

    expected = output_root / "diagnostics" / "run_manifest.latest.json"
    assert path == expected
    assert expected.exists()
    payload = json.loads(expected.read_text(encoding="utf-8"))
    assert payload["run_id"] == "r1"
