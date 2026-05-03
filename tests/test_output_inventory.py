"""Tests for output artifact classification and inventory helpers."""

from __future__ import annotations

from pathlib import Path

from analysis.diagnostics.output_artifact_policy import classify_relative_path
from analysis.diagnostics.output_inventory import build_inventory_rows


def test_classify_run_manifest_is_evidence_required() -> None:
    meta = classify_relative_path("run_manifest.json")
    assert meta["artifact_bucket"] == "evidence_required"


def test_classify_unknown_defaults_optional() -> None:
    meta = classify_relative_path("diagnostics/foo_bar_unknown.xyz")
    assert meta["artifact_bucket"] == "diagnostics_optional"


def test_build_inventory_rows_counts_files(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "r1"
    (run_root / "diagnostics").mkdir(parents=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (run_root / "diagnostics" / "note.txt").write_text("x", encoding="utf-8")
    rows = build_inventory_rows(run_root)
    assert len(rows) == 2
    kinds = {r["path"]: r["artifact_type"] for r in rows}
    assert kinds["run_manifest.json"] == "evidence_required"
