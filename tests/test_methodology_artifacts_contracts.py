"""Tests for methodology contract exports and output-hygiene mirroring."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from config import app_config
from obsidiandroid.orchestration import methodology_artifacts


@pytest.fixture()
def run_diagnostics_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """``.../output/runs/<id>/diagnostics`` so local ``*.latest.*`` mirrors are suppressed."""
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(tmp_path / "output"), raising=False)
    rid = "rid_methodology"
    diag = tmp_path / "output" / "runs" / rid / "diagnostics"
    diag.mkdir(parents=True)
    return diag


def _global_diagnostics(run_diagnostics_dir: Path) -> Path:
    # .../output/runs/<rid>/diagnostics -> .../output
    output_root = run_diagnostics_dir.parent.parent.parent
    return output_root / "diagnostics"


def test_export_feature_contract_suppresses_local_latest_json(run_diagnostics_dir: Path) -> None:
    df = pd.DataFrame({"a": [1], "b": [2]})
    out = methodology_artifacts.export_feature_contract(
        feature_df=df,
        run_id="rid_methodology",
        output_dir=str(run_diagnostics_dir),
    )
    assert Path(out).name == "feature_contract.json"
    assert (run_diagnostics_dir / "feature_contract_rid_methodology.json").is_file()
    assert not (run_diagnostics_dir / "feature_contract.latest.json").exists()
    g_latest = _global_diagnostics(run_diagnostics_dir) / "feature_contract.latest.json"
    assert g_latest.is_file()


def test_export_leakage_assessment_suppresses_local_latest_txt(run_diagnostics_dir: Path) -> None:
    df = pd.DataFrame({"parsed_family_x": [1]})
    out = methodology_artifacts.export_leakage_assessment(
        feature_df=df,
        run_id="rid_methodology",
        output_dir=str(run_diagnostics_dir),
    )
    assert Path(out).name == "leakage_assessment.txt"
    assert (run_diagnostics_dir / "leakage_assessment_rid_methodology.txt").is_file()
    assert not (run_diagnostics_dir / "leakage_assessment.latest.txt").exists()
    g_latest = _global_diagnostics(run_diagnostics_dir) / "leakage_assessment.latest.txt"
    assert g_latest.is_file()


def test_export_modality_contract_stamped_and_compat(run_diagnostics_dir: Path) -> None:
    fusion_df = pd.DataFrame({"perm__a": [1], "parsed_family_v": [0]})
    out = methodology_artifacts.export_modality_method_contract(
        permission_df=None,
        fusion_feature_df=fusion_df,
        run_id="rid_methodology",
        output_dir=str(run_diagnostics_dir),
    )
    assert Path(out).name == "modality_method_contract.json"
    stamped = run_diagnostics_dir / "modality_method_contract_rid_methodology.json"
    assert stamped.is_file()
    assert json.loads(stamped.read_text(encoding="utf-8"))["run_id"] == "rid_methodology"
    assert not (run_diagnostics_dir / "modality_method_contract.latest.json").exists()
