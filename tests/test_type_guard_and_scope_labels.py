"""Tests for type-guard suppression audit and support-gap surface labeling."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics.data_problem_quantification import (
    _prediction_error_metrics,
    _support_gap_metrics,
)
from obsidiandroid.reporting.type_guard_suppression_audit import (
    compose_type_guard_suppression_audit,
    summarize_type_guard_suppressions,
)


def test_summarize_type_guard_marks_already_incorrect() -> None:
    frame = pd.DataFrame(
        [
            {
                "family_canonical_expected": "SpyNote",
                "raw_model_predicted_family": "BankBot",
                "predicted_family": "other",
                "type_slug_expected": "rat",
                "override_tag": "type_guard_family_suppressed",
            },
            {
                "family_canonical_expected": "Triada",
                "raw_model_predicted_family": "Joker",
                "predicted_family": "other",
                "type_slug_expected": "backdoor",
                "override_tag": "type_guard_family_suppressed",
            },
        ]
    )
    summary = summarize_type_guard_suppressions(frame)
    assert summary["type_guard_suppressed_count"] == 2
    assert summary["raw_model_already_incorrect_count"] == 2
    assert summary["raw_model_would_have_matched_family_count"] == 0
    assert summary["all_demotions_were_already_incorrect"] is True


def test_compose_type_guard_audit(tmp_path: Path) -> None:
    run_id = "tg_fix"
    run_root = tmp_path / "run"
    diag = run_root / "diagnostics"
    diag.mkdir(parents=True)
    (run_root / "run_manifest.json").write_text(json.dumps({"run_status": "complete"}), encoding="utf-8")
    pd.DataFrame(
        [
            {
                "sample_id": 1,
                "family_canonical_expected": "SpyNote",
                "predicted_family": "other",
                "raw_model_predicted_family": "BankBot",
                "override_tag": "type_guard_family_suppressed",
                "type_slug_expected": "rat",
                "classification_label": "x",
            },
            {
                "sample_id": 2,
                "family_canonical_expected": "Godfather",
                "predicted_family": "Cerberus",
                "raw_model_predicted_family": "Cerberus",
                "override_tag": "",
                "type_slug_expected": "banker",
                "classification_label": "x",
            },
        ]
    ).to_csv(diag / f"prediction_errors_{run_id}.csv", index=False)
    payload = compose_type_guard_suppression_audit(run_root=run_root, run_id=run_id)
    assert payload["type_guard_suppressed_count"] == 1
    assert payload["report_status"] == "FINAL_FROM_COMPLETED_RUN"
    assert Path(payload["detail_csv"]).is_file()
    assert Path(payload["report_markdown"]).is_file()


def test_support_gap_prefers_aligned_labels(tmp_path: Path) -> None:
    run_id = "gap_fix"
    diag = tmp_path / "diagnostics"
    diag.mkdir(parents=True)
    # Post-support surface (would incorrectly yield empty gap).
    pd.DataFrame({"family": ["A", "B"], "sample_count": [50, 40]}).to_csv(
        diag / "family_distribution.csv", index=False
    )
    # Full aligned cohort with many sub-threshold families.
    rows = [{"sample_id": i, "family_canonical": f"F{i % 10}"} for i in range(100)]
    # Make F0..F4 have 2 samples each (below 20), F5..F9 have 18 each still below 20.
    rows = []
    sid = 0
    for fam_i in range(10):
        n = 2 if fam_i < 5 else 18
        for _ in range(n):
            rows.append({"sample_id": sid, "family_canonical": f"Fam{fam_i}"})
            sid += 1
    pd.DataFrame(rows).to_csv(diag / f"aligned_labels_{run_id}.csv", index=False)
    pd.DataFrame({"family": [f"Fam{i}" for i in range(5)]}).to_csv(
        diag / "low_support_families.csv", index=False
    )
    gap = _support_gap_metrics(diag, run_id, min_support=20)
    assert "aligned_labels" in str(gap.get("distribution_source", ""))
    assert int(gap["below_support_family_count"]) == 10
    assert int(gap["families_with_gap_le_5"]) >= 1
    assert int(gap["pretraining_families_below_runtime_min_support"]) == 5


def test_prediction_error_metrics_scope_raw_and_guard(tmp_path: Path) -> None:
    run_id = "err_fix"
    diag = tmp_path / "diagnostics"
    diag.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "family_canonical_expected": "spynote",
                "predicted_family": "other",
                "raw_model_predicted_family": "BankBot",
                "override_tag": "type_guard_family_suppressed",
            },
            {
                "family_canonical_expected": "spynote",
                "predicted_family": "other",
                "raw_model_predicted_family": "BankBot",
                "override_tag": "type_guard_family_suppressed",
            },
            {
                "family_canonical_expected": "godfather",
                "predicted_family": "Cerberus",
                "raw_model_predicted_family": "Cerberus",
                "override_tag": "",
            },
        ]
    ).to_csv(diag / f"prediction_errors_{run_id}.csv", index=False)
    metrics = _prediction_error_metrics(diag, run_id)
    assert metrics["type_guard_suppressed_count"] == 2
    assert metrics["top_error_pair"]["predicted_family"] == "other"
    assert metrics["top_error_pair"]["scope"] == "post_type_guard"
    assert metrics["top_error_pair_raw_model"]["predicted_family"] == "BankBot"
    assert metrics["top_error_pair_raw_model"]["scope"] == "raw_model"
