"""Tests for shared operator-state resolution."""

from __future__ import annotations

import json
from pathlib import Path

from config import app_config

from obsidiandroid.cli.menu import operator_state


def test_build_operator_state_respects_run_override_and_best_index_fallback(tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_root = out_root / "runs" / run_id
    (run_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (out_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "profile_params": {"profile_id": "malicious_temporal_stability"},
                "publication_ready_status": "unknown",
            }
        ),
        encoding="utf-8",
    )
    (run_root / "run_evidence_index.md").write_text("# evidence\n", encoding="utf-8")

    shared = operator_state.build_operator_state(output_base=out_root, run_id=run_id)

    assert shared["latest_run_id"] == run_id
    assert shared["profile_id"] == "malicious_temporal_stability"
    assert shared["best_run_index_path"] == run_root / "run_evidence_index.md"
    assert shared["has_canonical_run_science"] is False


def test_build_operator_state_reports_canonical_run_science_when_present(tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_root = out_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "profile_params": {"profile_id": "malicious_temporal_stability"}}),
        encoding="utf-8",
    )
    (diagnostics_dir / "run_science_index.md").write_text("# science\n", encoding="utf-8")

    shared = operator_state.build_operator_state(output_base=out_root, run_id=run_id)

    assert shared["best_run_index_path"] == diagnostics_dir / "run_science_index.md"
    assert shared["has_canonical_run_science"] is True


def test_build_operator_state_exposes_cohort_contract_highlights(tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_root = out_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "profile_params": {"profile_id": "paper2_demo"}}),
        encoding="utf-8",
    )
    (diagnostics_dir / f"cohort_filter_contract_{run_id}.json").write_text(
        json.dumps({"cohort_gates": {"min_malicious_detections": 5}}),
        encoding="utf-8",
    )
    (diagnostics_dir / f"analysis_snapshot_filter_summary_{run_id}.csv").write_text(
        "mode,source_total,post_filter_total\npaper_locked_snapshot_membership,100,98\n",
        encoding="utf-8",
    )
    (diagnostics_dir / f"cohort_gate_counts_{run_id}.csv").write_text(
        (
            "run_id,step,gate_name,count_before,count_after,dropped,details\n"
            f"{run_id},1,paper_locked_snapshot_membership,100,98,2,"
            "\"sample_id lock applied before dataset/contract gates\"\n"
            f"{run_id},2,min_malicious_detections,98,97,1,"
            "\">=5; rescued_unknown_consensus=3\"\n"
        ),
        encoding="utf-8",
    )

    shared = operator_state.build_operator_state(output_base=out_root, run_id=run_id)

    assert shared["cohort_membership_mode"] == "paper_locked_snapshot_membership"
    assert "sample_id lock applied" in str(shared["cohort_membership_authority_note"])
    assert shared["min_malicious_detections_threshold"] == 5
    assert shared["min_malicious_detections_rescued_unknown_consensus"] == 3


def test_build_operator_state_exposes_cohort_lock_status(tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_root = out_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "publication_ready_status": "READY",
                "paper_cohort_contract": {"cohort_lock_status": "count_only_incomplete_sample_lock"},
            }
        ),
        encoding="utf-8",
    )

    shared = operator_state.build_operator_state(output_base=out_root, run_id=run_id)

    assert shared["cohort_lock_status"] == "count-only"


def test_build_operator_state_exposes_taxonomy_label_drift(tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_root = out_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "publication_ready_status": "READY",
                "paper_cohort_contract": {
                    "cohort_lock_status": "membership_locked_taxonomy_drift",
                    "sample_id_lock": {
                        "taxonomy_label_drift": {
                            "drift_class": "taxonomy_expansion",
                            "family_delta": 5,
                            "type_delta": 1,
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    shared = operator_state.build_operator_state(output_base=out_root, run_id=run_id)

    assert shared["cohort_lock_status"] == "taxonomy-drift"
    assert shared["taxonomy_label_drift"]["drift_class"] == "taxonomy_expansion"


def test_build_operator_state_respects_dict_shaped_evidence_mode_false(tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_root = out_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "evidence_mode": {"resolved_value": False, "source": "profile"},
                "paper_mode": {"resolved_value": False, "source": "profile"},
                "publication_ready_status": "NOT_APPLICABLE",
            }
        ),
        encoding="utf-8",
    )

    shared = operator_state.build_operator_state(output_base=out_root, run_id=run_id)

    assert shared["evidence_mode"] is False
    assert shared["publication_ready_mode"] is False


def test_build_operator_state_exposes_display_mode_from_debug_flag(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Operator state should expose the shared display mode."""
    monkeypatch.setattr(app_config, "DEBUG_MODE", True, raising=False)

    shared = operator_state.build_operator_state(output_base=tmp_path / "output")

    assert shared["display_mode"] == "debug"


def test_build_operator_state_distinguishes_diagnostics_from_provenance(tmp_path: Path) -> None:
    """Runs with diagnostics artifacts should not be reported as completely missing."""
    out_root = tmp_path / "output"
    run_id = "20260601T142735Z__2a924a"
    run_root = out_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "profile_params": {"profile_id": "android_malware_major_families"}}),
        encoding="utf-8",
    )
    (diagnostics_dir / "pipeline_stage_timings.latest.csv").write_text(
        "stage,duration_sec\nsamples,49.3\n",
        encoding="utf-8",
    )

    shared = operator_state.build_operator_state(output_base=out_root, run_id=run_id)

    assert shared["latest_run_has_diagnostics"] is True
    assert shared["latest_run_has_provenance"] is False
