"""Tests for headline vs ablation feature contract parity helpers."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from obsidiandroid.diagnostics.headline_ablation_parity import build_feature_contract_comparison


def test_build_feature_contract_comparison_merges_evaluation_contract(tmp_path: Path) -> None:
    rid = "run_xyz"
    diag = tmp_path / "diagnostics"
    diag.mkdir(parents=True)
    (diag / f"evaluation_contract_{rid}.json").write_text(
        json.dumps(
            {
                "split_contract": {"split_hash": "splith"},
                "label_authority": {
                    "display_label_field": "family_canonical",
                    "training_label_field": "family_id",
                    "active_training_classes": 51,
                },
                "feature_contract": {"headline_feature_column_hash": "hhh"},
            }
        ),
        encoding="utf-8",
    )
    ab = diag / f"ablation_summary_{rid}.csv"
    with ab.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["experiment", "label_target", "model", "feature_column_hash"])
        w.writerow(["full_fused", "family_canonical_default", "random_forest", "aaa"])

    out = build_feature_contract_comparison(diag, rid, manifest_context=None)
    assert out["headline_feature_column_hash"] == "hhh"
    assert out["ablation_full_fused_feature_column_hash"] == "aaa"
    assert out["apples_to_apples"] is False
    assert out["split_hash"] == "splith"
    assert "51" in (out.get("label_target") or "")

