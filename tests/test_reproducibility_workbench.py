"""Tests for reproducibility_workbench path resolution (non-slow)."""

from __future__ import annotations

import json
from pathlib import Path

from obsidiandroid.diagnostics import reproducibility_workbench as rw


def test_pick_first_existing_prefers_run_scoped_run_paths_manifest(tmp_path: Path) -> None:
    """Run-scoped manifest should satisfy check before global diagnostics."""
    run_id = "20260303T000000Z__abc123"
    run_diag = tmp_path / "output" / "runs" / run_id / "diagnostics"
    global_diag = tmp_path / "output" / "diagnostics"
    run_diag.mkdir(parents=True, exist_ok=True)
    global_diag.mkdir(parents=True, exist_ok=True)
    run_scoped = run_diag / f"run_paths_manifest_{run_id}.json"
    run_scoped.write_text("{}", encoding="utf-8")
    picked, tried = rw.pick_first_existing(
        [run_diag / f"run_paths_manifest_{run_id}.json", global_diag / f"run_paths_manifest_{run_id}.json"]
    )
    assert picked == run_scoped
    assert tried and tried[0] == str(run_scoped)


def test_feature_contract_candidates_include_unsuffixed_run_scoped_json(tmp_path: Path) -> None:
    """Pipeline writes ``feature_contract.json`` under run diagnostics (not only suffixed names)."""
    run_id = "20260505T214806Z__911a64"
    out = tmp_path / "output"
    rdiag = out / "runs" / run_id / "diagnostics"
    rdiag.mkdir(parents=True)
    canonical = rdiag / "feature_contract.json"
    canonical.write_text('{"run_id": "x"}', encoding="utf-8")
    candidates = [
        rdiag / "feature_contract.json",
        rdiag / "feature_contract.latest.json",
        rdiag / f"feature_contract_{run_id}.json",
    ]
    picked, _ = rw.pick_first_existing(candidates)
    assert picked == canonical


def test_ablation_macro_f1_reads_feature_set_ablation_summary(tmp_path: Path) -> None:
    rid = "20260303T000000Z__abc123"
    p = tmp_path / "feature_set_ablation_summary.csv"
    p.write_text(
        "model,experiment,label_target,macro_f1_score\n"
        "rf,permissions_raw,family_id,0.91\n"
        "rf,full_fused,family_id,0.92\n",
        encoding="utf-8",
    )
    got = rw._ablation_macro_f1_by_experiment(tmp_path, rid)
    assert abs((got.get("permissions_raw") or 0) - 0.91) < 1e-6
    assert abs((got.get("full_fused") or 0) - 0.92) < 1e-6


def test_collect_run_comparison_row_includes_cohort_methodology(tmp_path: Path) -> None:
    out = tmp_path / "output"
    run_id = "20260303T000000Z__abc123"
    run_root = out / "runs" / run_id
    rdiag = run_root / "diagnostics"
    gdiag = out / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    gdiag.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        (
            '{"run_id":"%s","publication_ready_status":"READY","paper_cohort_contract":'
            '{"cohort_lock_status":"count_only_incomplete_sample_lock"},'
            '"profile_params":{"profile_id":"paper2_demo"}}'
        )
        % run_id,
        encoding="utf-8",
    )
    (run_root / "run_summary.json").write_text('{"profile_id":"paper2_demo"}', encoding="utf-8")
    (rdiag / f"cohort_filter_contract_{run_id}.json").write_text(
        '{"cohort_gates":{"min_malicious_detections":5}}',
        encoding="utf-8",
    )
    (rdiag / f"analysis_snapshot_filter_summary_{run_id}.csv").write_text(
        "mode,source_total,post_filter_total\npaper_locked_snapshot_membership,100,98\n",
        encoding="utf-8",
    )
    (rdiag / f"cohort_gate_counts_{run_id}.csv").write_text(
        (
            "run_id,step,gate_name,count_before,count_after,dropped,details\n"
            f"{run_id},1,min_malicious_detections,98,97,1,"
            "\">=5; rescued_unknown_consensus=3\"\n"
        ),
        encoding="utf-8",
    )

    row = rw.collect_run_comparison_row(out, run_id)

    assert row["publication_ready_status"] == "READY"
    assert row["cohort_lock_status"] == "count-only"
    assert row["cohort_membership_mode"] == "paper_locked_snapshot_membership"
    assert row["min_malicious_detections_threshold"] == 5
    assert row["rescued_unknown_consensus"] == 3


def test_write_run_comparison_summary_preserves_methodology_columns(tmp_path: Path) -> None:
    out = tmp_path / "output"
    gdiag = out / "diagnostics"
    gdiag.mkdir(parents=True, exist_ok=True)
    for run_id in ("r1", "r2"):
        run_root = out / "runs" / run_id
        rdiag = run_root / "diagnostics"
        rdiag.mkdir(parents=True, exist_ok=True)
        (run_root / "run_manifest.json").write_text(
            (
                '{"run_id":"%s","publication_ready_status":"NOT_APPLICABLE",'
                '"profile_params":{"profile_id":"dev_smoke"}}'
            )
            % run_id,
            encoding="utf-8",
        )
        (run_root / "run_summary.json").write_text('{"profile_id":"dev_smoke"}', encoding="utf-8")
        (rdiag / f"cohort_filter_contract_{run_id}.json").write_text(
            '{"cohort_gates":{"min_malicious_detections":2}}',
            encoding="utf-8",
        )
        (rdiag / f"cohort_gate_counts_{run_id}.csv").write_text(
            (
                "run_id,step,gate_name,count_before,count_after,dropped,details\n"
                f"{run_id},1,min_malicious_detections,10,10,0,"
                "\">=2; rescued_unknown_consensus=1\"\n"
            ),
            encoding="utf-8",
        )

    csv_path, md_path = rw.write_run_comparison_summary(output_root=out, run_ids=["r1", "r2"])

    csv_text = csv_path.read_text(encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")
    assert "cohort_lock_status" in csv_text
    assert "cohort_membership_mode" in csv_text
    assert "rescued_unknown_consensus" in csv_text
    assert "cohort_lock_status" in md_text
    assert "rescued_unknown_consensus" in md_text


def test_write_research_validity_review_uses_global_taxonomy_and_latest_mirrors(tmp_path: Path) -> None:
    """Review payload should preserve paper-facing taxonomy counts and global latest mirror availability."""
    out = tmp_path / "output"
    run_id = "r_valid"
    rdiag = out / "runs" / run_id / "diagnostics"
    gdiag = out / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    gdiag.mkdir(parents=True, exist_ok=True)

    (gdiag / "taxonomy_consistency_summary.latest.json").write_text(
        json.dumps(
            {
                "taxonomy_mismatch_count": 12,
                "paper_facing_taxonomy_mismatch_count": 2,
                "type_mismatch_count": 9,
                "type_missing_label_count": 2,
                "type_noncanonical_count": 1,
                "family_label_mismatch_count": 0,
                "prediction_error_count": 1,
            }
        ),
        encoding="utf-8",
    )
    (gdiag / "headline_vs_ablation_contract_comparison.latest.md").write_text("ok", encoding="utf-8")
    (gdiag / "taxonomy_type_authority_review.latest.md").write_text("ok", encoding="utf-8")

    review_json, _review_md = rw.write_research_validity_review(output_root=out, run_id=run_id)

    payload = json.loads(review_json.read_text(encoding="utf-8"))
    assert payload["taxonomy"]["paper_facing_taxonomy_mismatch_count"] == 2
    assert payload["artifacts_used"]["headline_vs_ablation_contract_comparison"] is True
    assert payload["artifacts_used"]["taxonomy_type_authority_review"] is True
