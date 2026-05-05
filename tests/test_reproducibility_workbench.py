"""Tests for reproducibility_workbench path resolution (non-slow)."""

from __future__ import annotations

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
