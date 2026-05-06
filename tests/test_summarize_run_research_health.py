"""Tests for summarize_run_research_health diagnostics script."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.diagnostics.summarize_run_research_health import gather_report


def test_gather_report_metrics_parity_hashes_match_when_equal(tmp_path: Path) -> None:
    run_id = "parity_match_run"
    run_root = tmp_path / run_id
    diag = run_root / "diagnostics"
    diag.mkdir(parents=True)

    shared = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    (diag / f"evaluation_contract_{run_id}.json").write_text(
        json.dumps({"feature_contract": {"headline_feature_column_hash": shared}}),
        encoding="utf-8",
    )
    ablation = diag / f"ablation_summary_{run_id}.csv"
    with ablation.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["experiment", "label_target", "model", "feature_column_hash"])
        w.writerow(["vendor_full", "family_canonical_default", "random_forest", "other"])
        w.writerow(["full_fused", "family_canonical_default", "random_forest", shared])

    report = gather_report(tmp_path, run_root)
    parity = report["metrics_comparison_parity"]
    assert parity["headline_vs_ablation_full_fused_hashes_match"] is True
    assert parity["headline_feature_column_hash"] == shared
    assert parity["ablation_full_fused_family_feature_column_hash"] == shared


def test_gather_report_metrics_parity_mismatch_adds_hint(tmp_path: Path) -> None:
    run_id = "parity_mismatch_run"
    run_root = tmp_path / run_id
    diag = run_root / "diagnostics"
    diag.mkdir(parents=True)

    (diag / f"evaluation_contract_{run_id}.json").write_text(
        json.dumps({"feature_contract": {"headline_feature_column_hash": "aaa"}}),
        encoding="utf-8",
    )
    ablation = diag / f"ablation_summary_{run_id}.csv"
    with ablation.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["experiment", "label_target", "model", "feature_column_hash"])
        w.writerow(["full_fused", "family_canonical_default", "random_forest", "bbb"])

    report = gather_report(tmp_path, run_root)
    parity = report["metrics_comparison_parity"]
    assert parity["headline_vs_ablation_full_fused_hashes_match"] is False
    hints = report.get("operator_hints") or []
    assert any("full_fused" in h.lower() and "hash" in h.lower() for h in hints)


def test_gather_report_taxonomy_type_mapping_breakdown(tmp_path: Path) -> None:
    run_id = "tax_breakdown_run"
    run_root = tmp_path / run_id
    diag = run_root / "diagnostics"
    diag.mkdir(parents=True)

    lines = (
        "sample_id,mismatch_reason,type_slug_expected,label_type_slug\n"
        "1,type_mapping_mismatch,dropper,banker\n"
        "2,type_mapping_mismatch,dropper,banker\n"
        "3,type_mapping_mismatch,worm,ransomware\n"
        "4,other_reason,dropper,banker\n"
    )
    (diag / f"taxonomy_consistency_mismatches_{run_id}.csv").write_text(lines, encoding="utf-8")

    report = gather_report(tmp_path, run_root)
    br = report.get("taxonomy_type_mapping_breakdown") or {}
    assert br.get("type_mapping_mismatch_rows") == 3
    pairs = br.get("top_pairs") or []
    assert pairs[0] == {"cohort_type_slug": "dropper", "label_type_slug": "banker", "count": 2}


@pytest.mark.parametrize(
    ("headline_missing", "ablation_missing", "expect_match"),
    [
        (True, False, None),
        (False, True, None),
    ],
)
def test_gather_report_parity_unknown_when_partial_inputs(
    tmp_path: Path, headline_missing: bool, ablation_missing: bool, expect_match: bool | None
) -> None:
    run_id = "parity_partial_run"
    run_root = tmp_path / run_id
    diag = run_root / "diagnostics"
    diag.mkdir(parents=True)

    if not headline_missing:
        (diag / f"evaluation_contract_{run_id}.json").write_text(
            json.dumps({"feature_contract": {"headline_feature_column_hash": "h1"}}),
            encoding="utf-8",
        )
    if not ablation_missing:
        ablation = diag / f"ablation_summary_{run_id}.csv"
        with ablation.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["experiment", "label_target", "model", "feature_column_hash"])
            w.writerow(["full_fused", "family_canonical_default", "xgboost", "h2"])

    report = gather_report(tmp_path, run_root)
    assert report["metrics_comparison_parity"]["headline_vs_ablation_full_fused_hashes_match"] is expect_match
