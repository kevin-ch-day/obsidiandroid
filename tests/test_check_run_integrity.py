"""Tests for scripts/diagnostics/check_run_integrity.py Tier A QA helper."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.diagnostics import check_run_integrity


def test_compare_run_artifacts_aligned() -> None:
    man = {"run_id": "r1", "cohort_size": 100, "train_sample_count": 70, "test_sample_count": 30, "profile_params": {"profile_id": "p1"}}
    summ = {"top_model": "rf", "top_macro_f1": 0.77, "publication_ready_status": "NOT_APPLICABLE", "train_sample_count": 70}
    obs = {
        "run_id": "r1",
        "profile_id": "p1",
        "publication_ready_status": "NOT_APPLICABLE",
        "counts": {"governed_cohort_rows": 100, "train_rows": 70, "test_rows": 30},
        "model_summary": {"top_model": "rf", "top_macro_f1": 0.77},
        "model": {"top_model": "rf", "top_macro_f1": 0.77},
    }
    assert check_run_integrity.compare_run_artifacts(
        manifest=man, summary=summ, observability=obs, f1_tolerance=0.01
    ) == []


def test_compare_run_artifacts_detects_drift(tmp_path: Path) -> None:
    man = {"run_id": "r1", "cohort_size": 100, "train_sample_count": 70, "test_sample_count": 30, "profile_params": {"profile_id": "p1"}}
    summ = {"top_model": "rf", "top_macro_f1": 0.77, "cohort_size": 100, "train_sample_count": 70}
    obs = {
        "run_id": "r1",
        "profile_id": "p1",
        "counts": {"governed_cohort_rows": 99, "train_rows": 70, "test_rows": 30},
        "model_summary": {"top_model": "xgb", "top_macro_f1": 0.5},
        "model": {},
    }
    issues = check_run_integrity.compare_run_artifacts(
        manifest=man, summary=summ, observability=obs, f1_tolerance=0.01
    )
    blob = "\n".join(issues)
    assert "cohort_size mismatch" in blob
    assert "top_model mismatch" in blob


def test_cli_end_to_end_ok(tmp_path: Path) -> None:
    run = tmp_path / "runzz"
    diag = run / "diagnostics"
    diag.mkdir(parents=True)
    man = {
        "run_id": "r2",
        "cohort_size": 10,
        "train_sample_count": 6,
        "test_sample_count": 4,
        "profile_params": {"profile_id": "banker"},
        "split": {"train_sample_count": 6, "test_sample_count": 4},
    }
    summ = {
        "run_id": "r2",
        "cohort_size": 10,
        "train_sample_count": 6,
        "test_sample_count": 4,
        "top_model": "a",
        "top_macro_f1": 0.5,
        "publication_ready_status": "NOT_APPLICABLE",
    }
    obs = {
        "run_id": "r2",
        "profile_id": "banker",
        "publication_ready_status": "NOT_APPLICABLE",
        "counts": {"governed_cohort_rows": 10, "train_rows": 6, "test_rows": 4},
        "model_summary": {"top_model": "a", "top_macro_f1": 0.5},
    }
    (run / "run_manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (run / "run_summary.json").write_text(json.dumps(summ), encoding="utf-8")
    (diag / "run_observability_summary.json").write_text(json.dumps(obs), encoding="utf-8")
    old = sys.argv
    try:
        sys.argv = ["check_run_integrity.py", "--run-root", str(run)]
        assert check_run_integrity.main() == 0
    finally:
        sys.argv = old
