"""Tests for cohort contract filters in sample stage."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.pipeline import stage_samples
from analysis.pipeline.contract_filters import apply_contract_filters
from config import app_config


def test_apply_contract_filters_excludes_unknown_in_paper_mode(monkeypatch) -> None:
    """Paper mode should exclude unknown type_slug when no explicit override is set."""
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "type_slug": ["banker", "unknown", ""],
            "family_canonical": ["A", "B", "C"],
        }
    )
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", True, raising=False)

    out_df, gate_rows = apply_contract_filters(
        samples_df=samples_df,
        gates={},
        run_id="r1",
    )

    assert len(out_df) == 1
    assert out_df["sample_id"].tolist() == [1]
    assert any(row["gate_name"] == "exclude_unknown_type_slug" for row in gate_rows)


def test_apply_contract_filters_family_cap_and_min_malicious(monkeypatch) -> None:
    """Min-malicious and family-cap filters should be deterministic."""
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4, 5],
            "type_slug": ["banker"] * 5,
            "family_canonical": ["A", "A", "A", "B", "B"],
            "vt_malicious_count": [5, 3, 1, 9, 8],
            "vt_suspicious_count": [0, 0, 0, 0, 0],
        }
    )
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    gates = {"min_malicious_detections": 4, "family_cap": 1, "family_cap_seed": 42}

    out_df, _ = apply_contract_filters(
        samples_df=samples_df,
        gates=gates,
        run_id="r2",
    )

    # After min_malicious_detections>=4, remaining sample IDs: 1,4,5
    # Family cap=1 keeps one from A and one from B.
    assert len(out_df) == 2
    assert set(out_df["family_canonical"].tolist()) == {"A", "B"}


def test_export_cohort_filter_contract_writes_files(monkeypatch, tmp_path: Path) -> None:
    """Contract and gate-count files should be exported under diagnostics."""
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    contract_path, gate_path = stage_samples._export_cohort_filter_contract(  # pylint: disable=protected-access
        run_id="r3",
        profile_id="all_malicious",
        gates={"min_malicious_detections": 5},
        gate_rows=[{"run_id": "r3", "step": 1, "gate_name": "test", "count_before": 10, "count_after": 8, "dropped": 2, "details": ""}],
    )

    assert Path(contract_path).exists()
    assert Path(gate_path).exists()
    latest = Path(app_config.DEFAULT_OUTPUT_DIR) / "diagnostics" / "cohort_filter_contract.latest.json"
    assert latest.exists()


def test_export_time_window_family_distributions_skips_absent_legacy_families(
    monkeypatch, tmp_path: Path
) -> None:
    """Do not emit Devixor/Gigabud by-year files when those families are absent."""
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "", raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "", raising=False)
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_canonical": ["Irata", "Joker"],
            "effective_first_seen_year": [2024, 2025],
        }
    )

    artifacts = stage_samples._export_time_window_family_distributions(samples_df)  # pylint: disable=protected-access

    diagnostics_dir = Path(app_config.DEFAULT_OUTPUT_DIR) / "diagnostics"
    assert (diagnostics_dir / "family_distribution_by_year.csv").exists()
    assert not (diagnostics_dir / "devixor_by_year.csv").exists()
    assert not (diagnostics_dir / "gigabud_by_year.csv").exists()
    assert all("devixor_by_year.csv" not in path for path in artifacts)
    assert all("gigabud_by_year.csv" not in path for path in artifacts)


def test_export_cohort_lock_artifacts_writes_summary_and_membership(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Cohort stage should export canonical lock summary and membership artifacts."""
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "", raising=False)
    samples_df = pd.DataFrame(
        {
            "sample_id": [2, 1],
            "sha256": ["b", "a"],
            "family_canonical": ["FamB", "FamA"],
            "type_slug": ["banker", "banker"],
            "android_package_name": ["pkg.b", "pkg.a"],
        }
    )
    samples_df.attrs["snapshot_lock"] = {
        "status": "matched",
        "applied": True,
        "matched_sample_count": 2,
        "lock_sample_count": 2,
        "missing_from_db_count": 0,
        "fail_closed": True,
    }

    summary_path, membership_path = stage_samples._export_cohort_lock_artifacts(  # pylint: disable=protected-access
        samples_df=samples_df,
        run_id="r_lock",
        profile_id="paper2_primary",
        enable_snapshot_lock=True,
        evidence_strict_snapshot_lock=True,
        snapshot_lock_file="lock.csv",
        snapshot_file="snapshot.csv",
        snapshot_meta_file="snapshot.meta.txt",
        selection_rule_version="snapshot_v1",
        dataset_time_contract_path="dataset_time_contract.latest.json",
        cohort_ids_path="paper_cohort_sample_ids.csv",
    )

    summary_payload = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    membership_df = pd.read_csv(membership_path)
    assert Path(summary_path).exists()
    assert Path(membership_path).exists()
    assert summary_payload["sample_count"] == 2
    assert summary_payload["snapshot_lock"]["status"] == "matched"
    assert membership_df["sample_id"].tolist() == [1, 2]
