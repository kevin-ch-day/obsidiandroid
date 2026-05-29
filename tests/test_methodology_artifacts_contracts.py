"""Tests for methodology contract exports and output-hygiene mirroring."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from config import app_config
from obsidiandroid.orchestration import methodology_artifacts
from obsidiandroid.pipeline import sample_exports


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


def test_export_modality_method_contract_writes_expected_fields(run_diagnostics_dir: Path) -> None:
    """Exporter should emit modality payload with raw/fusion dimensions and hashes."""
    permission_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "perm__internet": [1, 1],
            "perm__read_sms": [0, 1],
            "perm__dangerous_count": [0, 1],
        }
    )
    fusion_df = pd.DataFrame(
        {
            "parsed_family_vendor_a": [1, 2],
            "threat_class_vendor_a": [0, 1],
            "malware_type_vendor_a": [0, 1],
            "perm__internet": [1, 1],
            "perm__read_sms": [0, 1],
            "meta__vt_tag_count": [3, 5],
        },
        index=[1, 2],
    )

    out = methodology_artifacts.export_modality_method_contract(
        permission_df=permission_df,
        fusion_feature_df=fusion_df,
        run_id="run_modality",
        output_dir=str(run_diagnostics_dir),
    )
    out_path = Path(out)
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run_modality"
    assert payload["permission_modality"]["feature_count_raw"] == 3
    assert payload["av_modality"]["feature_count_in_fusion"] == 3
    assert payload["fusion_modality"]["feature_count_total"] == 6
    assert payload["fusion_modality"]["feature_count_permission"] == 2
    assert payload["fusion_modality"]["feature_count_other"] == 1


def test_methodology_exports_omit_stamped_run_duplicates_in_compact_mode(
    run_diagnostics_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", False, raising=False)

    df = pd.DataFrame({"a": [1], "parsed_family_x": [1]})
    fusion_df = pd.DataFrame({"perm__a": [1], "parsed_family_v": [0]})

    methodology_artifacts.export_feature_contract(
        feature_df=df,
        run_id="rid_methodology",
        output_dir=str(run_diagnostics_dir),
    )
    methodology_artifacts.export_leakage_assessment(
        feature_df=df,
        run_id="rid_methodology",
        output_dir=str(run_diagnostics_dir),
    )
    methodology_artifacts.export_modality_method_contract(
        permission_df=None,
        fusion_feature_df=fusion_df,
        run_id="rid_methodology",
        output_dir=str(run_diagnostics_dir),
    )

    assert (run_diagnostics_dir / "feature_contract.json").is_file()
    assert (run_diagnostics_dir / "leakage_assessment.txt").is_file()
    assert (run_diagnostics_dir / "modality_method_contract.json").is_file()
    assert not (run_diagnostics_dir / "feature_contract_rid_methodology.json").exists()
    assert not (run_diagnostics_dir / "leakage_assessment_rid_methodology.txt").exists()
    assert not (run_diagnostics_dir / "modality_method_contract_rid_methodology.json").exists()


def test_export_paper_cohort_sample_ids_skips_compact_non_paper_runs(
    run_diagnostics_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(
        app_config,
        "PAPER_COHORT_SAMPLE_IDS_FILE",
        str(run_diagnostics_dir / "paper_cohort_sample_ids.csv"),
        raising=False,
    )

    out = sample_exports.export_paper_cohort_sample_ids(pd.DataFrame({"sample_id": [1, 2, 2]}))

    assert out == ""
    assert not (run_diagnostics_dir / "paper_cohort_sample_ids.csv").exists()
