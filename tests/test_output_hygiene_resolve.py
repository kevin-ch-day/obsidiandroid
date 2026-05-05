"""Tests for output path resolution helpers."""

from __future__ import annotations

from pathlib import Path

from config import app_config
from obsidiandroid.common import output_hygiene as oh


def test_resolve_dataset_time_contract_prefers_run_scoped(tmp_path: Path) -> None:
    diag = tmp_path / "diagnostics"
    diag.mkdir()
    scoped = diag / "dataset_time_contract_r1.json"
    scoped.write_text("{}", encoding="utf-8")
    legacy = diag / "dataset_time_contract.latest.json"
    legacy.write_text("{}", encoding="utf-8")
    assert oh.resolve_dataset_time_contract_path(diag, "r1") == scoped


def test_resolve_analysis_snapshot_prefers_run_scoped(tmp_path: Path) -> None:
    diag = tmp_path / "diagnostics"
    diag.mkdir()
    scoped = diag / "analysis_snapshot_r2.csv"
    scoped.write_text("a,b\n1,2\n", encoding="utf-8")
    assert oh.resolve_analysis_snapshot_csv_path(diag, "r2") == scoped


def test_mirror_csv_writes_primary_and_secondary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(tmp_path / "output"), raising=False)
    diag = tmp_path / "output" / "runs" / "rid" / "diagnostics"
    diag.mkdir(parents=True)
    paths = oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diag,
        run_filename="foo_rid.csv",
        csv_text="x\n1\n",
        global_latest_name="foo.latest.csv",
    )
    assert len(paths) == 2
    assert paths[0].name == "foo_rid.csv"
    assert paths[0].exists()
    expected_global = tmp_path / "output" / "diagnostics" / "foo.latest.csv"
    assert paths[1].resolve() == expected_global.resolve()
