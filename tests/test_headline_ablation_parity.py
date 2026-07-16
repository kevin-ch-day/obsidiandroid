"""Tests for headline vs ablation feature contract parity helpers."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from obsidiandroid.diagnostics.headline_ablation_parity import build_feature_contract_comparison


def test_contract_comparison_rejects_other_run_artifacts(tmp_path: Path) -> None:
    """A run cannot inherit a model or ablation contract from a neighbor."""
    diag = tmp_path / "diagnostics"
    diag.mkdir(parents=True)
    (diag / "evaluation_contract_other.json").write_text(
        json.dumps({"feature_contract": {"headline_feature_column_hash": "other"}}),
        encoding="utf-8",
    )
    (diag / "model_comparison_summary_other.csv").write_text(
        "Model,headline_feature_column_hash\nrandom_forest,other\n",
        encoding="utf-8",
    )
    (diag / "ablation_summary_other.csv").write_text(
        "experiment,label_target,feature_column_hash\nfull_fused,family_id,other\n",
        encoding="utf-8",
    )

    out = build_feature_contract_comparison(diag, "active")
    assert out["headline_feature_column_hash"] is None
    assert out["ablation_full_fused_feature_column_hash"] is None


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


def test_build_feature_contract_comparison_prefers_family_id_full_fused_hash_when_available(tmp_path: Path) -> None:
    rid = "run_family_id"
    diag = tmp_path / "diagnostics"
    diag.mkdir(parents=True)
    (diag / f"evaluation_contract_{rid}.json").write_text(
        json.dumps(
            {
                "label_authority": {
                    "display_label_field": "family_canonical",
                    "training_label_field": "family_id",
                    "active_training_classes": 18,
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
        w.writerow(["full_fused", "family_canonical_default", "random_forest", "display_hash"])
        w.writerow(["full_fused", "family_id", "random_forest", "authority_hash"])

    out = build_feature_contract_comparison(diag, rid, manifest_context=None)
    assert out["ablation_full_fused_feature_column_hash"] == "authority_hash"


def test_build_feature_contract_comparison_reports_extra_headline_modalities(tmp_path: Path) -> None:
    rid = "run_extra_modalities"
    diag = tmp_path / "diagnostics"
    diag.mkdir(parents=True)
    feature_contract_path = diag / "feature_contract.json"
    feature_contract_path.write_text(
        json.dumps(
            {
                "feature_columns": [
                    "parsed_family_vendor_a_FakeCall",
                    "threat_class_vendor_a_banker",
                    "perm__android.permission.INTERNET",
                    "meta__permissions",
                    "meta__vt_consensus_score",
                    "meta__package_name_length",
                ]
            }
        ),
        encoding="utf-8",
    )
    (diag / f"evaluation_contract_{rid}.json").write_text(
        json.dumps(
            {
                "feature_contract": {
                    "headline_feature_column_hash": "hhh",
                    "headline_feature_contract_path": str(feature_contract_path),
                }
            }
        ),
        encoding="utf-8",
    )
    ab = diag / f"ablation_summary_{rid}.csv"
    with ab.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["experiment", "label_target", "model", "feature_column_hash"])
        w.writerow(["full_fused", "family_id", "random_forest", "aaa"])

    out = build_feature_contract_comparison(diag, rid, manifest_context=None)

    assert out["headline_permission_feature_count"] == 2
    assert out["headline_vendor_semantic_feature_count"] == 2
    assert out["headline_extra_non_vendor_permission_feature_count"] == 2
    assert "additional non-vendor/non-permission feature column(s)" in out["incommensurable_message"]
