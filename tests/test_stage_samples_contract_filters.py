"""Tests for cohort contract filters in sample stage."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.pipeline import contract_filters
from obsidiandroid.pipeline import stage_samples
from obsidiandroid.governance.cohort_lock_manifest import validate_lock_manifest
from obsidiandroid.governance.label_snapshot_contract import label_snapshot_hash
from config import app_config

apply_contract_filters = contract_filters.apply_contract_filters


def test_package_integrity_respects_profile_threshold_in_strict_mode(monkeypatch) -> None:
    """Strict mode should honor profile threshold when missing package is allowed."""
    monkeypatch.setattr(stage_samples.app_config, "RUNTIME_EVIDENCE_STRICT_MODE", True, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "EVIDENCE_HARD_FAIL_MISSING_PACKAGE", True, raising=False)
    df = pd.DataFrame(
        {
            "android_package_name": ["pkg.a", "", "pkg.b", ""],
        }
    )
    stage_samples._assert_package_name_integrity(  # pylint: disable=protected-access
        samples_df=df,
        gates={"allow_missing_package_name": True, "max_missing_package_pct": 60.0},
    )


def test_package_integrity_hard_fails_when_missing_not_allowed_in_strict_mode(monkeypatch) -> None:
    """Strict mode should enforce 0% when missing package names are disallowed."""
    monkeypatch.setattr(stage_samples.app_config, "RUNTIME_EVIDENCE_STRICT_MODE", True, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "EVIDENCE_HARD_FAIL_MISSING_PACKAGE", True, raising=False)
    df = pd.DataFrame(
        {
            "android_package_name": ["pkg.a", ""],
        }
    )
    with pytest.raises(ValueError, match="Missing package rate"):
        stage_samples._assert_package_name_integrity(  # pylint: disable=protected-access
            samples_df=df,
            gates={"allow_missing_package_name": False, "max_missing_package_pct": 100.0},
        )


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


def test_apply_contract_filters_rejects_textual_null_and_id_shaped_family_targets(monkeypatch) -> None:
    """A numeric ID alone must not promote a placeholder into a training family."""
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "family_id": [11, 12, 13],
            "family_canonical": ["nan", "family_id=12", "NamedFamily"],
            "type_slug": ["banker", "banker", "banker"],
        }
    )
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)

    out_df, gate_rows = apply_contract_filters(
        samples_df=samples_df,
        gates={"require_mapped_family": True},
        run_id="mapped_guard",
    )

    assert out_df["sample_id"].tolist() == [3]
    guard = next(row for row in gate_rows if row["gate_name"] == "require_mapped_family_target_guard")
    assert guard["dropped"] == 2


def test_apply_contract_filters_treats_known_aliases_as_same_family(monkeypatch) -> None:
    """Conflict exclusion must retain aliases while removing substantive label drift."""
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "family_label_raw": ["Wroba", "BlackLoan", "SpyC23"],
            "family_canonical": ["RoamingMantis", "SpyLoan", "HiddenAd"],
            "type_slug": ["banker", "banker", "adware"],
        }
    )
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)

    out_df, gate_rows = apply_contract_filters(
        samples_df=samples_df,
        gates={"exclude_family_label_conflicts": True},
        run_id="alias_conflict_guard",
    )

    assert out_df["sample_id"].tolist() == [1, 2]
    conflict_gate = next(row for row in gate_rows if row["gate_name"] == "exclude_family_label_conflicts")
    assert conflict_gate["dropped"] == 1
    assert "alias_aware" in conflict_gate["details"]


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


def test_apply_contract_filters_family_cap_recognizes_sql_applied_cap(monkeypatch) -> None:
    """Family-cap bookkeeping should not claim fresh drops when SQL already enforced the cap."""
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 4],
            "type_slug": ["banker", "banker"],
            "family_canonical": ["A", "B"],
            "vt_malicious_count": [5, 9],
            "vt_suspicious_count": [0, 0],
        }
    )
    samples_df.attrs["family_cap_applied_in_sql"] = True
    samples_df.attrs["family_cap_sql_value"] = 1
    samples_df.attrs["family_cap_sql_seed"] = 42

    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    out_df, gate_rows = apply_contract_filters(
        samples_df=samples_df,
        gates={"family_cap": 1, "family_cap_seed": 42},
        run_id="r2_sql_cap",
    )

    assert len(out_df) == 2
    family_cap_gate = next(row for row in gate_rows if row["gate_name"] == "family_cap")
    assert family_cap_gate["dropped"] == 0
    assert "already_applied_in_sql" in family_cap_gate["details"]


def test_apply_contract_filters_type_cap_recognizes_sql_applied_cap(monkeypatch) -> None:
    """Type-cap bookkeeping should not claim fresh drops when SQL already enforced the cap."""
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "type_slug": ["banker", "rat", "spyware"],
            "family_canonical": ["A", "B", "C"],
            "vt_malicious_count": [5, 9, 7],
            "vt_suspicious_count": [0, 0, 0],
        }
    )
    samples_df.attrs["type_cap_applied_in_sql"] = True
    samples_df.attrs["type_cap_sql_value"] = 1
    samples_df.attrs["type_cap_sql_seed"] = 42

    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    out_df, gate_rows = apply_contract_filters(
        samples_df=samples_df,
        gates={"type_cap": 1, "type_cap_seed": 42},
        run_id="r2_sql_type_cap",
    )

    assert len(out_df) == 3
    type_cap_gate = next(row for row in gate_rows if row["gate_name"] == "type_cap")
    assert type_cap_gate["dropped"] == 0
    assert "already_applied_in_sql" in type_cap_gate["details"]


def test_apply_contract_filters_type_cap_by_slug_recognizes_sql_applied_cap(monkeypatch) -> None:
    """Per-type quota bookkeeping should not claim fresh drops when SQL already enforced them."""
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "type_slug": ["banker", "rat", "spyware"],
            "family_canonical": ["A", "B", "C"],
            "vt_malicious_count": [5, 9, 7],
            "vt_suspicious_count": [0, 0, 0],
        }
    )
    samples_df.attrs["type_cap_by_slug_applied_in_sql"] = True
    samples_df.attrs["type_cap_by_slug_sql_value"] = {"banker": 1, "rat": 1}

    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    out_df, gate_rows = apply_contract_filters(
        samples_df=samples_df,
        gates={"type_cap_by_slug": {"banker": 1, "rat": 1}, "type_cap_seed": 42},
        run_id="r2_sql_type_cap_by_slug",
    )

    assert len(out_df) == 3
    gate = next(row for row in gate_rows if row["gate_name"] == "type_cap_by_slug")
    assert gate["dropped"] == 0
    assert "already_applied_in_sql" in gate["details"]


def test_apply_contract_filters_min_malicious_rescues_unknown_consensus_malware() -> None:
    """Rows with missing VT counts should survive when malware taxonomy still marks them malicious."""
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "type_slug": ["banker", "", "banker"],
            "family_canonical": ["Alien", "", "Cerberus"],
            "vt_malicious_count": [pd.NA, 0, 5],
            "vt_suspicious_count": [pd.NA, 0, 0],
            "vt_suggested_label": ["trojan.bankbot/alien", "", ""],
        }
    )

    out_df, gate_rows = apply_contract_filters(
        samples_df=samples_df,
        gates={"min_malicious_detections": 1},
        run_id="r_rescue",
    )

    assert out_df["sample_id"].tolist() == [1, 3]
    min_gate = next(row for row in gate_rows if row["gate_name"] == "min_malicious_detections")
    assert "rescued_unknown_consensus=1" in min_gate["details"]


def test_apply_contract_filters_min_family_label_confidence_score_excludes_noisy_rows(
    monkeypatch,
) -> None:
    """Confidence-sieving gate should drop rows below the configured family-label score."""
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "type_slug": ["banker", "banker", "rat"],
            "family_canonical": ["A", "A", "B"],
            "family_label_raw": ["A", "WrongA", "B"],
            "category_primary": ["trojan", "trojan", "rat"],
            "category_subtype": ["banker", "spyware", "rat"],
            "sample_label_kind": [
                "family_or_common_name",
                "family_or_common_name",
                "family_or_common_name",
            ],
            "vt_family_token": ["a", "a", "b"],
        }
    )
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)

    out_df, gate_rows = apply_contract_filters(
        samples_df=samples_df,
        gates={"min_family_label_confidence_score": 80, "min_samples_per_family": 2},
        run_id="r_conf",
    )

    assert out_df["sample_id"].tolist() == [1, 3]
    conf_gate = next(row for row in gate_rows if row["gate_name"] == "min_family_label_confidence_score")
    assert conf_gate["dropped"] == 1
    assert ">=80" in conf_gate["details"]


def test_export_cohort_filter_contract_writes_files(monkeypatch, tmp_path: Path) -> None:
    """Contract and gate-count files should be exported under diagnostics."""
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    contract_path, gate_path = stage_samples._export_cohort_filter_contract(  # pylint: disable=protected-access
        run_id="r3",
        profile_id="malicious_temporal_stability",
        gates={"min_malicious_detections": 5},
        gate_rows=[{"run_id": "r3", "step": 1, "gate_name": "test", "count_before": 10, "count_after": 8, "dropped": 2, "details": ""}],
    )

    assert Path(contract_path).exists()
    assert Path(gate_path).exists()
    latest = Path(app_config.DEFAULT_OUTPUT_DIR) / "diagnostics" / "cohort_filter_contract.latest.json"
    assert latest.exists()


def test_export_cohort_filter_contract_run_scoped_uses_global_latest(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    """Run-scoped cohort contract exports should avoid local latest duplicates."""
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("r3")
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "r3", raising=False)
    contract_path, gate_path = stage_samples._export_cohort_filter_contract(  # pylint: disable=protected-access
        run_id="r3",
        profile_id="malicious_temporal_stability",
        gates={"min_malicious_detections": 5},
        gate_rows=[
            {
                "run_id": "r3",
                "step": 1,
                "gate_name": "test",
                "count_before": 10,
                "count_after": 8,
                "dropped": 2,
                "details": "",
            }
        ],
    )

    assert Path(contract_path).exists()
    assert Path(gate_path).exists()
    assert not (diagnostics_dir / "cohort_filter_contract.latest.json").exists()
    assert not (diagnostics_dir / "cohort_gate_counts.latest.csv").exists()
    assert (output_root / "diagnostics" / "cohort_filter_contract.latest.json").exists()
    assert (output_root / "diagnostics" / "cohort_gate_counts.latest.csv").exists()


def test_export_cohort_filter_contract_slot_run_uses_runtime_diagnostics_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Slot-based runs should keep the stamped contract under the active runtime diagnostics dir."""
    output_root = tmp_path / "output"
    diagnostics_dir = output_root / "runs" / "majorfam_benchmark" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (output_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "20260604T041505Z__fd0a06", raising=False)

    contract_path, gate_path = stage_samples._export_cohort_filter_contract(  # pylint: disable=protected-access
        run_id="20260604T041505Z__fd0a06",
        profile_id="android_malware_major_families",
        gates={"min_malicious_detections": 1},
        gate_rows=[
            {
                "run_id": "20260604T041505Z__fd0a06",
                "step": 1,
                "gate_name": "test",
                "count_before": 10,
                "count_after": 10,
                "dropped": 0,
                "details": "",
            }
        ],
    )

    assert Path(contract_path).resolve().parent == diagnostics_dir.resolve()
    assert Path(gate_path).resolve().parent == diagnostics_dir.resolve()
    assert not (output_root / "diagnostics" / "cohort_filter_contract_20260604T041505Z__fd0a06.json").exists()
    assert (output_root / "diagnostics" / "cohort_filter_contract.latest.json").exists()


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
        profile_id="malicious_temporal_stability",
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
    manifest_path = Path(summary_payload["artifacts"]["cohort_lock_manifest_json"])
    assert manifest_path.exists()
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert summary_payload["sample_count"] == 2
    assert summary_payload["snapshot_lock"]["status"] == "matched"
    assert membership_df["sample_id"].tolist() == [1, 2]
    assert manifest_payload["sample_count"] == 2
    assert manifest_payload["cohort_hash"]
    label_snapshot_path = Path(summary_payload["artifacts"]["label_snapshot_csv"])
    assert label_snapshot_path.exists()
    label_snapshot_df = pd.read_csv(label_snapshot_path)
    assert label_snapshot_df["sample_id"].tolist() == [1, 2]
    assert manifest_payload["label_snapshot_path"] == str(label_snapshot_path)
    assert manifest_payload["label_snapshot_hash"] == label_snapshot_hash(label_snapshot_df)
    assert manifest_payload["taxonomy_hash"] == manifest_payload["label_snapshot_hash"]
    assert summary_payload["label_snapshot"]["taxonomy_hash_source"] == "row_level_label_snapshot"
    validate_lock_manifest(manifest=manifest_payload, manifest_path=manifest_path)

    # A declared row-level label snapshot is part of the lock, not optional
    # informational output.  Tampering must fail validation before reuse.
    label_snapshot_df.loc[0, "family_canonical"] = "MutatedFamily"
    label_snapshot_df.to_csv(label_snapshot_path, index=False)
    with pytest.raises(ValueError, match="label_snapshot_hash mismatch"):
        validate_lock_manifest(manifest=manifest_payload, manifest_path=manifest_path)


def test_export_cohort_lock_artifacts_marks_live_db_drift_as_count_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Lock summary should reflect degraded count-only semantics when locked ids are missing from DB."""
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
        "lock_sample_count": 3,
        "missing_from_db_count": 1,
        "fail_closed": True,
    }

    summary_path, _ = stage_samples._export_cohort_lock_artifacts(  # pylint: disable=protected-access
        samples_df=samples_df,
        run_id="r_lock",
        profile_id="malicious_temporal_stability_locked",
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
    assert summary_payload["snapshot_lock"]["status"] == "count_only_incomplete_sample_lock"
    assert summary_payload["snapshot_lock"]["selection_status"] == "matched"
    assert summary_payload["snapshot_lock"]["missing_from_db_count"] == 1
